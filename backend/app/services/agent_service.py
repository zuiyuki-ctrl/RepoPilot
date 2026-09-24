from uuid import UUID

from ..agent.context import AgentEventSink, AgentRunContext
from ..agent.state import ReadonlyAgentState, PlanningAgentState
from ..agent.graph import READONLY_AGENT_GRAPH, PLANNING_AGENT_GRAPH
from ..schemas.plan import ChangePlan

from .repository_service import get_repository

from ..agent.policy import (
    AGENT_SYSTEM_PROMPT,
    MAX_TOOL_RESULT_CHARS,
    PLAN_RESEARCH_SYSTEM_PROMPT
)



# 查询仓库并协调模型与只读工具；不存在返回 None，无证据则返回明确的不足说明。
# 工具执行次数和所有工具结果字符数都有上限；可恢复的读取失败交给模型纠正。
# 数据库/网络等基础设施故障仍向外传播，不伪装成“未找到代码”。
def run_readonly_agent(
    repository_id: UUID,
    *,
    question: str,
    max_tool_calls: int = 4,
    event_sink: AgentEventSink | None = None
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
        },
        context=AgentRunContext(event_sink=event_sink),
    )
    result = final_state["result"]

    if result is None:
        raise RuntimeError("Readonly agent graph completed without a result")

    return result


def run_planning_agent(
    repository_id: UUID,
    *,
    user_request: str,
    max_tool_calls: int = 4,
    event_sink: AgentEventSink | None = None,
) -> ChangePlan | None:
    # 1. 清理并校验 user_request。
    #    strip 后长度必须为 1～1000。
    normalized_request = user_request.strip()
    if not 1 <= len(normalized_request) <= 1000:
        raise ValueError("user_request must be between 1 and 1000 characters")

    # 2. 校验 max_tool_calls 为 1～8。
    if not 1 <= max_tool_calls <= 8:
        raise ValueError("max_tool_calls must be between 1 and 8")

    # 3. 调用 get_repository(repository_id)
    repository = get_repository(repository_id)
    if repository is None:
        return None

    # 4. 创建 PlanningAgentState。
    initial_state: PlanningAgentState = {
        "repository_id": repository_id,
        "max_tool_calls": max_tool_calls,

        # 研究阶段仍使用现有只读系统提示。
        "messages": [
            {"role": "system", "content": PLAN_RESEARCH_SYSTEM_PROMPT },
            {"role": "user", "content": normalized_request},
        ],
        "tool_trace": [],
        "sources": [],

        "used_calls": 0,
        "remaining_chars": MAX_TOOL_RESULT_CHARS,
        "output_exhausted": False,
        "allow_tools": True,

        # PlanningAgentState 继承的现有最终结果字段。
        "result": None,

        # 计划流程新增字段。
        "user_request": normalized_request,
        "plan": None,
    }

    # 5. 在数据库事务之外调用计划 Graph。
    final_state: PlanningAgentState = PLANNING_AGENT_GRAPH.invoke(
        initial_state,
        config={
            "recursion_limit": 32,
        },
        context=AgentRunContext(event_sink=event_sink),
    )

    # 6. 取得最终计划。
    plan = final_state["plan"]

    # 7. Graph 正常结束却没有计划时抛 RuntimeError。
    if plan is None:
        raise RuntimeError(
            "Planning agent graph completed without a plan"
        )

    # 8. 返回 ChangePlan。
    return plan
