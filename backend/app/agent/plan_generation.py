import json

from .planning import parse_change_plan
from .policy import PLAN_FINAL_INSTRUCTION, PLAN_SYSTEM_PROMPT
from ..rag.generation import request_tool_turn
from ..schemas.agent import AgentSourceReference
from ..schemas.plan import ChangePlan


def generate_change_plan(
    user_request: str,
    *,
    evidence_messages: list[dict],
    sources: list[AgentSourceReference],
) -> ChangePlan:
    # 1. 去除用户需求首尾空白。
    normalized_request = user_request.strip()

    # 2. 检查需求长度为 1～1000。
    #    检查 evidence_messages 非空。
    #    检查 sources 非空。
    #    任一条件不满足时抛 ValueError，且不能调用模型。
    if not (1 <= len(normalized_request) <= 1000 and evidence_messages and sources):
        raise ValueError("invalid request")

    # 3. 创建新的消息列表，第一条必须是计划系统提示。
    messages = [
        {
            "role": "system",
            "content": PLAN_SYSTEM_PROMPT,
        }
    ]

    # 4. 按原顺序复制证据消息。
    #    跳过 role="system" 的消息。
    #    每条保留消息使用 dict(message) 浅拷贝。
    for message in evidence_messages:
        if message["role"] == "system":
            continue

        messages.append(dict(message))

    # 5. 将允许引用的来源转换成可 JSON 序列化的数据。
    allowed_sources = [
        source.model_dump(mode="json")
        for source in sources
    ]

    # 6. 取得 ChangePlan 的 JSON Schema。
    output_schema = ChangePlan.model_json_schema()

    # 7. 构造计划请求消息。
    #    必须明确包含用户需求、允许引用的来源和输出格式。
    #    来源与 Schema 分别使用 json.dumps(..., ensure_ascii=False)。
    plan_request = (
        f"用户需求：\n{normalized_request}\n\n"
        f"允许引用的来源：\n{json.dumps(allowed_sources, ensure_ascii=False)}\n\n"
        f"输出格式：\n{json.dumps(output_schema, ensure_ascii=False)}"
    )
    messages.append(
        {
            "role": "user",
            "content": plan_request,
        }
    )

    # 8. 发起一次禁用工具的模型请求。
    assistant_message = request_tool_turn(
        messages,
        allow_tools=False,
        final_instruction=PLAN_FINAL_INSTRUCTION,
    )

    # 9. 将模型 content 交给已有解析器。
    plan = parse_change_plan(
        assistant_message["content"],
        sources=sources,
    )

    # 10. 返回通过结构及业务规则校验的计划。
    return plan