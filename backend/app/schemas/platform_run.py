"""v2 协议：传输模型不依赖内置 Plan、AgentTask 或检索服务。"""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, model_validator

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Lifecycle = Literal['queued', 'preparing', 'running', 'awaiting_input', 'evaluating', 'finished', 'interrupted']
Execution = Literal['pending', 'completed', 'failed', 'timed_out', 'cancelled', 'unknown']
Outcome = Literal['pending', 'passed', 'not_passed', 'unknown']
CapabilityName = Literal['execution', 'tests', 'diff', 'model_usage', 'tool_trace',
                         'retrieval', 'context', 'planning', 'reflection']


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CapabilityEvidence(ProtocolModel):
    declared: bool = False
    validated: bool = False
    availability: Literal['available', 'partial', 'missing', 'unsupported', 'invalid'] = 'unsupported'
    occurrence: Literal['occurred', 'not_occurred', 'unknown'] = 'unknown'
    source: Literal['platform', 'adapter', 'agent_reported'] = 'platform'
    evidence_sequences: list[int] = Field(default_factory=list)
    expected_records: int | None = Field(default=None, ge=0)
    recorded_records: int = Field(default=0, ge=0)

    @model_validator(mode='after')
    def coherent(self):
        if any(type(n) is not int or n < 1 for n in self.evidence_sequences):
            raise ValueError('Evidence sequences must be positive integers')
        if len(set(self.evidence_sequences)) != len(self.evidence_sequences):
            raise ValueError('Evidence sequences must be unique')
        if self.expected_records is not None and self.recorded_records > self.expected_records:
            raise ValueError('Recorded count exceeds expected count')
        if self.occurrence == 'not_occurred' and self.recorded_records:
            raise ValueError('An unexecuted stage cannot have stage records')
        if self.availability == 'available' and not self.evidence_sequences:
            raise ValueError('Available evidence requires references')
        return self


class AgentIdentity(ProtocolModel):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    adapter: Literal['native', 'process']
    implementation_sha256: Hash


class RunBudget(ProtocolModel):
    timeout_seconds: int = Field(default=600, ge=1, le=3600, strict=True)
    max_tool_calls: int | None = Field(default=None, ge=1, strict=True)
    max_tokens: int | None = Field(default=None, ge=1, strict=True)
    token_enforcement: Literal['advisory', 'enforced'] = 'advisory'


class AgentRunRequest(ProtocolModel):
    protocol_version: Literal[1] = 1
    run_id: UUID
    case_id: str = Field(min_length=1, max_length=100)
    case_version: str = Field(min_length=1, max_length=100)
    task_description: str = Field(min_length=1, max_length=10000)
    repository_commit: str = Field(pattern=r'^[0-9a-f]{40}$')
    # 逻辑挂载点；不允许调用方指定任意主机目录。
    workspace: Literal['/workspace'] = '/workspace'
    agent: AgentIdentity
    config_sha256: Hash
    case_sha256: Hash
    task_type: Literal['bug_fix', 'feature']
    rule_sha256: Hash
    environment_sha256: Hash
    initial_snapshot_hash: Hash
    editable_files: list[str] = Field(min_length=1)
    budget: RunBudget = Field(default_factory=RunBudget)

    @model_validator(mode='after')
    def relative_edit_scope(self):
        if len(set(self.editable_files)) != len(self.editable_files):
            raise ValueError('Editable paths must be unique')
        for value in self.editable_files:
            path = PurePosixPath(value)
            if (not value or '\\' in value or ':' in value or path.is_absolute()
                    or any(part in ('', '.', '..') for part in value.split('/'))):
                raise ValueError('Editable files must be normalized repository-relative paths')
        return self


class AgentRunResult(ProtocolModel):
    protocol_version: Literal[1] = 1
    run_id: UUID
    execution_status: Literal['completed', 'failed', 'timed_out', 'cancelled', 'awaiting_input']
    agent: AgentIdentity
    error_code: str | None = Field(default=None, max_length=100)
    # 这里没有 success、passed 或 Evaluation 字段。具体产物传输由 Process Adapter 实现。


class ObservationSummary(ProtocolModel):
    protocol_version: Literal[1] = 1
    level: Literal['unknown', 'L0', 'L1', 'L2']
    completeness: Literal['complete', 'partial']
    capabilities: dict[CapabilityName, CapabilityEvidence]


class RunRead(ProtocolModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)
    id: UUID
    repository_id: UUID
    legacy_task_id: UUID | None
    case_id: str
    case_version: str
    agent: AgentIdentity
    lifecycle: Lifecycle
    execution_status: Execution
    evaluation_outcome: Outcome
    version: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    observation: ObservationSummary


class RunEventRead(ProtocolModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)
    id: UUID
    run_id: UUID
    sequence: int
    event_type: str
    source: Literal['platform', 'adapter', 'agent_reported']
    created_at: datetime
    # Day 1 只返回生命周期元信息，不公开任意 payload、路径或配置。


class RunPage(ProtocolModel):
    source: Literal['live'] = 'live'
    items: list[RunRead]


class RunEventPage(ProtocolModel):
    source: Literal['live'] = 'live'
    items: list[RunEventRead]
    next_after_sequence: int
