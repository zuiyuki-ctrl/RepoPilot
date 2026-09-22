from uuid import UUID

from ..agent.state import ReadonlyAgentState
from ..agent.graph import READONLY_AGENT_GRAPH

from .repository_service import get_repository

from ..agent.policy import (
    AGENT_SYSTEM_PROMPT,
    MAX_TOOL_RESULT_CHARS,
)



# 查询仓库并协调模型与只读工具；不存在返回 None，无证据则返回明确的不足说明。
# 工具执行次数和所有工具结果字符数都有上限；可恢复的读取失败交给模型纠正。
# 数据库/网络等基础设施故障仍向外传播，不伪装成“未找到代码”。
def run_readonly_agent(
    repository_id: UUID,
    *,
    question: str,
    max_tool_calls: int = 4,
) -> dict | None:
    # 1. question 去掉首尾空白，要求长度为 1～1000。
    # max_tool_calls 要求为 1～8。
    question = question.strip()
    if not 1 <= len(question) <= 1000:
        raise ValueError("question must be between 1 and 1000 characters")

    if not 1 <= max_tool_calls <= 8:
        raise ValueError("max_tool_calls must be between 1 and 8")

    # 2. 使用 get_repository(repository_id) 检查仓库。
    # 不存在返回 None，避免先花费模型调用。
    repository = get_repository(repository_id)
    if repository is None:
        return None

    initial_state: ReadonlyAgentState = {
        "repository_id": repository_id,
        "max_tool_calls": max_tool_calls,

        "messages": [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "tool_trace": [],
        "sources": [],

        "used_calls": 0,
        "remaining_chars": MAX_TOOL_RESULT_CHARS,
        "output_exhausted": False,
        "allow_tools": True,

        "result": None,
    }

    final_state: ReadonlyAgentState = READONLY_AGENT_GRAPH.invoke(
        initial_state,
        config={
            "recursion_limit": 32
        }
    )
    result = final_state["result"]

    if result is None:
        raise RuntimeError("Readonly agent graph completed without a result")

    return result
