"""运行前声明的实验约定；不从历史结果反推规则。"""
from typing import Literal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator, model_serializer
from .experiment_decision import DecisionPolicy


class RequiredTest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    classname: str = Field(min_length=1)
    name: str = Field(min_length=1)


class AcceptanceRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1)
    required_tests: list[RequiredTest] = Field(min_length=1)
    baseline_failure_tests: list[RequiredTest] = Field(default_factory=list)
    manual_criteria: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_tests(self):
        required = {(t.classname, t.name) for t in self.required_tests}
        failures = {(t.classname, t.name) for t in self.baseline_failure_tests}
        if len(required) != len(self.required_tests) or len(failures) != len(self.baseline_failure_tests):
            raise ValueError("Test identities must be unique")
        if not failures <= required:
            raise ValueError("Baseline failure tests must be required final tests")
        if any(not c.strip() for c in self.manual_criteria) or len(set(self.manual_criteria)) != len(self.manual_criteria):
            raise ValueError("Manual criteria must be nonempty and unique")
        return self


class ExperimentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    suite_id: str = Field(min_length=1)
    suite_version: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    repeat_index: int = Field(ge=1, strict=True)
    changed_parameter: Literal["retrieval_policy"] = "retrieval_policy"
    baseline: Literal["vector"] = "vector"
    candidate: Literal["hybrid"] = "hybrid"
    max_tool_calls: int = Field(default=4, ge=1, le=8, strict=True)
    # 当前业务默认重试预算为 1；实验脚本不自动启动修复轮次。
    max_retries: Literal[1] = 1
    test_timeout_seconds: Literal[120] = 120
    intervention_policy: Literal["approve_generated_candidate_only"] = "approve_generated_candidate_only"
    acceptance: AcceptanceRule
    decision_policy: DecisionPolicy | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_contract(self, handler):
        result = handler(self)
        # 新可选字段不能改变旧定义的规范序列化与已冻结 SHA256。
        if self.decision_policy is None:
            result.pop("decision_policy", None)
        return result


class AcceptanceReview(BaseModel):
    """终态后的人工验收依据，与计划审批是两件事。"""
    model_config = ConfigDict(extra="forbid")
    task_id: UUID
    test_run_id: UUID
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: str = Field(min_length=1)
    recorded_at: datetime
    decision: Literal["approved", "rejected"]
    checked_criteria: list[str]
    evidence: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_record(self):
        if self.recorded_at.tzinfo is None or not self.reviewer.strip() or not self.evidence.strip():
            raise ValueError("Review requires timezone, reviewer and evidence")
        if len(self.checked_criteria) != len(set(self.checked_criteria)):
            raise ValueError("Reviewed criteria must be unique")
        return self
