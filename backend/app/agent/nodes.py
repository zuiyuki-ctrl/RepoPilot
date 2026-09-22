# 三个节点及路由函数
import json
from typing import Literal

from .evidence import finish_answer, prepare_evidence
from ..agent.state import ReadonlyAgentState
from ..core.exceptions import RepositoryScanError, FileSkippedError
from ..rag.generation import request_tool_turn
from .policy import BUDGET_ERROR, MAX_TOOL_ERROR_CHARS
from ..services.tool_service import execute_readonly_tool

import logging

logger = logging.getLogger(__name__)


def model_node(state: ReadonlyAgentState) -> dict:
    # 1. 根据次数、字符预算和 output_exhausted 计算 allow_tools。
    budget_error_size = len(json.dumps(BUDGET_ERROR, ensure_ascii=False))
    allow_tools = (
        state["used_calls"] < state["max_tool_calls"]
        and not state["output_exhausted"]
        and state["remaining_chars"] >= budget_error_size
    )

    # 2. 调用 request_tool_turn。
    assistant_message = request_tool_turn(
        state["messages"],
        allow_tools=allow_tools,
    )

    # 3. 返回追加 assistant 消息后的 messages，以及 allow_tools。
    # 当前 State 没有追加 reducer，messages 会被返回的新列表替换。
    # 创建新列表，不直接 append 到传入的 state 上。
    return {
        "messages": [*state["messages"], assistant_message],
        "allow_tools": allow_tools,
    }



def route_after_model(
    state: ReadonlyAgentState,
) -> Literal["tools", "finish"]:
    last_message = state["messages"][-1]

    # 1. 检查 messages[-1] 中是否有非空 tool_calls。
    if last_message.get("tool_calls"):
        return "tools"

    # 2. 有则返回 tools，否则返回 finish。
    else:
        return "finish"



def tools_node(state: ReadonlyAgentState) -> dict:
    # 1. 从最后一条 assistant 消息取出本批 tool_calls。
    tool_calls = state["messages"][-1]["tool_calls"]

    # 2. 将需要更新的列表复制到局部变量。
    messages = list(state["messages"])
    tool_trace = list(state["tool_trace"])
    sources = list(state["sources"])

    # 3. 保留调用前的 allow_tools 和整批错误消息预算检查。
    used_calls = state["used_calls"]
    remaining_chars = state["remaining_chars"]
    output_exhausted = state["output_exhausted"]

    budget_error_text = json.dumps(BUDGET_ERROR, ensure_ascii=False)
    budget_error_size = len(budget_error_text)

    if not state["allow_tools"]:
        raise ValueError("Model requested tools after the tool budget was exhausted")

    if remaining_chars < budget_error_size * len(tool_calls):
        raise ValueError("Too many tool calls for the remaining tool-result budget")

    # 4. 搬入现有 for call_index, call in enumerate(tool_calls) 循环。
    for call_index, call in enumerate(tool_calls):
        function_name = call["function"]["name"]
        arguments_text = call["function"]["arguments"]

        # 第一阶段：决定是否真正执行工具
        if used_calls >= state["max_tool_calls"] or output_exhausted:
            result = dict(BUDGET_ERROR)
        else:
            # 一旦开始处理这次调用，即使参数错误，也要消耗调用次数
            used_calls += 1

            try:
                args = json.loads(arguments_text)

                if not isinstance(args, dict):
                    raise ValueError("argument must be a dict")

                result = execute_readonly_tool(
                    state["repository_id"],
                    tool_name=function_name,
                    arguments=args,
                )

            except RepositoryScanError:
                # 记录 warning，不要把底层文件系统信息暴露给模型
                logger.warning(
                    "Agent source read failed; repository_id=%s",
                    state["repository_id"],
                    exc_info=True,
                )
                result = {
                    "error": "Cannot read requested source; check the path or search again"
                }

            except (ValueError, FileSkippedError, SyntaxError) as exc:
                # 将错误字符串限制在 MAX_TOOL_ERROR_CHARS
                result = {
                    "error": str(exc)[:MAX_TOOL_ERROR_CHARS],
                }

        # 第二阶段：从成功结果中准备候选证据
        result, pending_sources = prepare_evidence(
            function_name,
            result,
            len(sources),
        )

        result_text = json.dumps(result, ensure_ascii=False)

        # 第三阶段：检查字符预算
        calls_after_current = len(tool_calls) - call_index - 1
        reserved_chars = calls_after_current * budget_error_size

        if len(result_text) > remaining_chars - reserved_chars:
            # 1. 将 result 换成 BUDGET_ERROR
            result = dict(BUDGET_ERROR)

            # 2. result_text 换成 budget_error_text
            result_text = budget_error_text

            # 3. 清空 pending_sources
            pending_sources = []

            # 4. 将 output_exhausted 设为 True
            output_exhausted = True

        remaining_chars -= len(result_text)

        # 只有实际发给模型的证据才能进入 sources
        sources.extend(pending_sources)

        # 第四阶段：添加协议要求的 tool 消息
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result_text,
            }
        )

        # 第五阶段：记录实际发送给模型的结果
        tool_trace.append(
            {
                "tool_call_id": call["id"],
                "tool_name": function_name,
                "arguments": arguments_text,
                "result": result,
            }
        )


    # 5. 返回更新后的消息、记录、证据及预算字段。
    return {
        "messages": messages,
        "tool_trace": tool_trace,
        "sources": sources,
        "used_calls": used_calls,
        "remaining_chars": remaining_chars,
        "output_exhausted": output_exhausted,
    }


def finish_node(state: ReadonlyAgentState) -> dict:
    # 1. 从最后一条 assistant 消息取得 content。
    content = state["messages"][-1]["content"]

    # 2. 调用 finish_answer，传入 sources 和 tool_trace。
    result = finish_answer(content, state["sources"], state["tool_trace"])

    # 3. 返回 {"result": 校验后的结果}。
    return {"result": result}
