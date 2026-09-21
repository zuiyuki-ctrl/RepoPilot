from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..schemas.agent import AgentQuestionResponse


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_id: UUID
    user_request: str = Field(min_length=1, max_length=1000)
    task_type: Literal["question"] = Field(default="question")


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repository_id: UUID
    user_request: str
    task_type: str
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    result: AgentQuestionResponse | None
    error: str | None