"""可冻结的批次门槛与独立人工采用记录；不内置通用通过阈值。"""
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class PairIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    case_id: str = Field(min_length=1)
    case_version: str = Field(min_length=1)
    repeat_index: int = Field(ge=1, strict=True)


class DecisionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    version: str = Field(min_length=1)
    declared_at: AwareDatetime
    expected_pairs: list[PairIdentity] = Field(min_length=1)
    min_pairs: int = Field(ge=1, strict=True)
    min_classification_coverage: float = Field(gt=0, le=1)
    max_regressions: int = Field(ge=0, strict=True)
    min_quality_delta_pp: float = Field(ge=-100, le=100)
    min_resource_coverage: float = Field(gt=0, le=1)
    max_token_increase_percent: float | None = Field(default=None, ge=-100)
    max_cost_increase_percent: float | None = Field(default=None, ge=-100)
    max_wall_time_increase_percent: float | None = Field(default=None, ge=-100)
    cost_currency: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_batch(self):
        keys = {(p.case_id, p.case_version, p.repeat_index) for p in self.expected_pairs}
        if len(keys) != len(self.expected_pairs) or self.min_pairs > len(keys):
            raise ValueError("Expected pairs must be unique and cover min_pairs")
        if self.max_cost_increase_percent is not None and not self.cost_currency:
            raise ValueError("Cost threshold requires an explicit currency")
        return self


class DecisionReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: str = Field(min_length=1)
    recorded_at: AwareDatetime
    action: Literal["adopt_candidate", "keep_baseline", "continue_experiment"]
    rationale: str = Field(min_length=1)
