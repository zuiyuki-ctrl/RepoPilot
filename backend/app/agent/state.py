from typing import TypedDict
from uuid import UUID

from ..schemas.plan import ChangePlan


class ReadonlyAgentState(TypedDict):
    # 1. 固定输入：
    repository_id: UUID
    max_tool_calls: int

    # 2. 对话与执行记录：
    messages: list[dict]
    tool_trace: list[dict]
    sources: list[dict]

    # 3. 预算：
    used_calls: int
    remaining_chars: int
    output_exhausted: bool
    allow_tools: bool

    # 4. 最终结果：
    result: dict | None

class PlanningAgentState(ReadonlyAgentState):
    # 用户最初提出的修改需求。
    user_request: str

    # 计划节点生成的结构化计划；进入节点前为 None。
    plan: ChangePlan | None