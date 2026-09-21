from typing import TypedDict
from uuid import UUID


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