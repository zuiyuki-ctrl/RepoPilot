from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .plan import ChangePlan
from ..schemas.agent import AgentQuestionResponse


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_id: UUID
    user_request: str = Field(min_length=1, max_length=1000)
    task_type: Literal["question", "plan"] = Field(default="question")

class TaskPlanResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_id: UUID
    plan: ChangePlan

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
    result: AgentQuestionResponse | TaskPlanResult | None
    error: str | None

    review_decision: Literal["approved", "rejected"] | None
    review_comment: str | None
    reviewed_at: datetime | None


# 用户的审核决定
class TaskPlanReviewRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    decision: Literal["approved", "rejected"]
    comment: str | None = Field(default=None, max_length=1000)