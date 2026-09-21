# 三个节点及路由函数
import json
from typing import Literal

from ..agent.state import ReadonlyAgentState
from ..rag.generation import request_tool_turn
from .policy import BUDGET_ERROR


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
    # 2. 将需要更新的列表复制到局部变量。
    # 3. 保留调用前的 allow_tools 和整批错误消息预算检查。
    # 4. 搬入现有 for call_index, call in enumerate(tool_calls) 循环。
    # 5. 返回更新后的消息、记录、证据及预算字段。
    ...


def finish_node(state: ReadonlyAgentState) -> dict:
    # 1. 从最后一条 assistant 消息取得 content。
    # 2. 调用 finish_answer，传入 sources 和 tool_trace。
    # 3. 返回 {"result": 校验后的结果}。
    ...
