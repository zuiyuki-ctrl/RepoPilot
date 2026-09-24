import httpx

from .tool_chat import TOOL_DEFINITIONS
from ..core import config
from .prompts import DEFAULT_FINAL_INSTRUCTION, QA_SYSTEM_PROMPT


# 实现基于证据生成回答
def generate_answer(question: str, context_text: str) -> str:
    # 1. 检查 question、context_text 非空白。
    # 检查 API Key、CHAT_BASE_URL、CHAT_MODEL 已配置。
    # 不符合要求时抛带说明的 ValueError。
    if not question.strip() or not context_text.strip():
        raise ValueError("question and context_text must not be blank")

    if not (config.DASHSCOPE_API_KEY and config.CHAT_BASE_URL and config.CHAT_MODEL):
        raise ValueError("configuration error")

    # 2. 拼接完整 URL
    url = config.CHAT_BASE_URL.rstrip("/") + "/chat/completions"

    # 3. 创建 headers，与 embedding 请求方式相同。
    headers = {
        "Authorization": f"Bearer {config.DASHSCOPE_API_KEY}",
        "Content-Type": "application/json"
    }

    # 4. 创建 messages：
    # 第一条 role="system"，content=SYSTEM_PROMPT。
    # 第二条 role="user"，content 同时包含问题和代码证据。
    # 用“问题：”“代码证据：”明确分段。
    messages = [
        {"role": "system", "content": QA_SYSTEM_PROMPT},
        {"role": "user", "content": f"问题：\n{question}\n\n代码证据：\n{context_text}"},
    ]

    # 5. 创建请求体，包含：
    # model=config.CHAT_MODEL
    # messages=上面的列表
    # stream=False
    # enable_thinking=False
    # max_tokens=1500
    request_body = {
        "model": config.CHAT_MODEL,
        "messages": messages,
        "stream": False,
        "enable_thinking": False,
        "max_tokens": 1500
    }

    with httpx.Client(timeout=60.0) as client:
        # 6. 发送 POST，请求体使用 json=request_body。
        # raise_for_status() 后，再读取 response.json()。
        response = client.post(url, json=request_body, headers=headers)
        response.raise_for_status()
        payload = response.json()

    # 7. 取得响应中的 choices，确认是非空列表。
    if not isinstance(payload, dict):
        raise ValueError("response must be a dict")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("choices must be a nonempty list")

    # 8. 取第一项：
    # 检查 finish_reason 为 "stop"。
    # 其他状态先抛 ValueError，避免把截断回答当作完整回答。
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ValueError("choice must be a dict")

    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("message must be a dict")

    if choice.get("finish_reason") != "stop":
        raise ValueError("finish_reason is not 'stop'")

    # 9. 从第一项的 message["content"] 取出回答。
    # 确认是非空白字符串，然后返回。
    answer = message.get("content")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("answer must be a nonblank string")
    return answer


# 负责与模型通信，接收回答或调用请求。
# 禁用工具时，仅在消息副本中追加收尾指令，省略工具参数；响应仍禁止工具调用。
def request_tool_turn(
        messages: list[dict],
        *,
        allow_tools: bool = True,
        final_instruction: str = DEFAULT_FINAL_INSTRUCTION
) -> dict:
    # 1. 检查 messages 非空。
    # 检查 API Key、CHAT_BASE_URL、CHAT_MODEL 已配置。
    if not messages:
        raise ValueError("messages must be a nonempty list")

    if not (config.DASHSCOPE_API_KEY and config.CHAT_BASE_URL and config.CHAT_MODEL):
        raise ValueError("configuration error")

    # 2. 构造 URL、headers、请求体
    url = config.CHAT_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.DASHSCOPE_API_KEY}",
        "Content-Type": "application/json"
    }
    request_body = {
        "model": config.CHAT_MODEL,
        "messages": messages,
        "stream": False,
        "enable_thinking": False,
        "max_tokens": 1500,
    }

    if allow_tools:
        request_body["tools"] = TOOL_DEFINITIONS
        request_body["tool_choice"] = "auto"
    else:
        if not isinstance(final_instruction, str) or not final_instruction.strip():
            raise ValueError("final_instruction must be a nonblank string")
        request_message = list(messages)
        request_message.append({
            "role": "user",
            "content": final_instruction,
        })
        request_body["messages"] = request_message

    # 3. 使用 httpx.Client(timeout=60.0) 发送请求。
    # raise_for_status() 后读取 JSON。
    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, json=request_body, headers=headers)
        response.raise_for_status()
        payload = response.json()

    # 4. 检查：
    # payload 是 dict；
    # choices 是非空 list；
    # choices[0] 是 dict；
    # message 是 dict，role 为 "assistant"。
    if not isinstance(payload, dict):
        raise ValueError("response must be a dict")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("choices must be a nonempty list")

    choice = choices[0]
    if not isinstance(choice, dict):
        raise ValueError("choice must be a dict")

    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("message must be a dict")

    role = message.get("role")
    if role != "assistant":
        raise ValueError("role must be 'assistant'")

    # 5. 根据 finish_reason 分支处理。
    #
    # "tool_calls"：
    #   allow_tools 必须为 True；
    #   tool_calls 必须是非空列表；
    #   逐项检查调用结构，要求见下面。
    #   返回包含 role、content、tool_calls 的字典。
    #
    # "stop"：
    #   不应携带非空 tool_calls；
    #   content 必须是非空白字符串；
    #   返回包含 role、content 的字典。
    #
    # 其他值：
    #   抛 ValueError，避免接收被截断或异常的结果。
    finish_reason = choice.get("finish_reason")
    tool_calls = message.get("tool_calls")

    content = message.get("content", "")
    if finish_reason == "tool_calls":
        if not allow_tools:
            raise ValueError("Model returned tool_calls while tools were disabled")

        if not isinstance(tool_calls, list) or not tool_calls:
            raise ValueError("tool_calls must be a nonempty list")

        seen_ids = set()

        for call in tool_calls:
            # call 必须是 dict，否则抛 ValueError。
            if not isinstance(call, dict):
                raise ValueError("tool_calls must be a dict")

            # 取出 id，要求是非空白字符串。
            # 如果已经在 seen_ids 中，拒绝；否则加入集合。
            _id = call.get("id")
            if not isinstance(_id, str) or not _id.strip():
                raise ValueError("ID must be a non-blank string")

            if _id in seen_ids:
                raise ValueError("tool_calls already seen")
            seen_ids.add(_id)

            # type 必须等于 "function"。
            _type = call.get("type")
            if _type != "function":
                raise ValueError("tool_calls must have type 'function'")

            # function 必须是 dict。
            function = call.get("function")
            if not isinstance(function, dict):
                raise ValueError("function must be a dict")

            # function 中的 name 必须是非空白字符串。
            name = function.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("tool_calls must have a name")

            # function 中的 arguments 必须是字符串。
            # 这里先不要 json.loads，后续调度循环负责解析。
            arguments = function.get("arguments")
            if not isinstance(arguments, str):
                raise ValueError("arguments must be a string")

        if content is not None and not isinstance(content, str):
            raise ValueError("tool-call content must be a string or None")

        return {
            "role": role,
            "content": content,
            "tool_calls": tool_calls,
        }

    elif finish_reason == "stop":
        if tool_calls:
            raise ValueError("stop response must not contain tool_calls")

        if not isinstance(content, str) or not content.strip():
            raise ValueError("content must be a nonblank string")

        return {
            "role": role,
            "content": content,
        }
    else:
        raise ValueError(f"Unsupported finish_reason: {finish_reason!r}")
