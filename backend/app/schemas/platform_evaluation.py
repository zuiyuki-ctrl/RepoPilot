"""仅供平台采集器使用的独立评测输入，不是 Agent 输出或公开提交接口。"""
from typing import Literal
from uuid import UUID
from pydantic import Field
from .platform_run import ProtocolModel, Hash, Execution
from .experiment_definition import AcceptanceRule


class TestEvidence(ProtocolModel):
    run_id: UUID
    test_run_id: UUID
    snapshot_hash: Hash
    environment_sha256: Hash
    image: str = Field(min_length=1)
    timeout_seconds: int = Field(ge=1, strict=True)
    status: Literal['running', 'finished', 'error']
    exit_code: int | None = None
    timed_out: bool = False
    error: str | None = None
    test_report: dict | None = None


class EvaluationInput(ProtocolModel):
    protocol_version: Literal[1] = 1
    run_id: UUID
    execution_status: Execution
    case_id: str = Field(min_length=1)
    case_version: str = Field(min_length=1)
    case_sha256: Hash
    task_type: Literal['bug_fix', 'feature']
    rule: AcceptanceRule
    environment_sha256: Hash
    initial_snapshot_hash: Hash
    final_snapshot_hash: Hash | None = None
    diff_sha256: Hash | None = None
    writers_stopped: bool | None = None
    diff_within_scope: bool | None = None
    protected_tests_intact: bool | None = None
    baseline_test: TestEvidence | None = None
    final_test: TestEvidence | None = None


class EvaluationDecision(ProtocolModel):
    protocol_version: Literal[1] = 1
    run_id: UUID
    outcome: Literal['passed', 'not_passed', 'unknown']
    reason: str
    rule_sha256: Hash
    evidence_sha256: Hash
    scope: Literal['declared_automated_tests_only'] = 'declared_automated_tests_only'
