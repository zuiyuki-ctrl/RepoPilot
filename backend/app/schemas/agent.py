from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    question: str = Field(min_length=1, max_length=1000)
    max_tool_calls: int = Field(default=4, ge=1, le=8)


class AgentSourceReference(BaseModel):
    source_id: str
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class AgentToolTraceRead(BaseModel):
    tool_call_id: str
    tool_name: str
    arguments: str
    result: dict[str, Any]


class AgentQuestionResponse(BaseModel):
    repository_id: UUID
    answer: str
    tool_trace: list[AgentToolTraceRead]
    sources: list[AgentSourceReference]