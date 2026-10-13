"""人工失败复核只补充分析，不改写任务状态、验收或可比性。"""
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


FailureCategory = Literal[
    "RETRIEVAL_FAILURE", "CONTEXT_FAILURE", "PLANNING_FAILURE", "TOOL_FAILURE",
    "EDIT_FAILURE", "TEST_FAILURE", "REASONING_FAILURE", "RECOVERY_FAILURE",
    "BUDGET_EXCEEDED", "APPROVAL_REJECTED", "CANCELLED", "UNKNOWN",
]


class FailureReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_id: UUID
    analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: str = Field(min_length=1)
    recorded_at: AwareDatetime
    primary_category: FailureCategory
    secondary_categories: list[FailureCategory] = Field(default_factory=list)
    hypothesis: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def unique_references(self):
        if (len(set(self.evidence_ids)) != len(self.evidence_ids)
                or len(set(self.secondary_categories)) != len(self.secondary_categories)
                or self.primary_category in self.secondary_categories):
            raise ValueError("Review references and categories must be unique")
        return self
