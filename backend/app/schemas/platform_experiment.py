from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator, model_serializer
from .platform_run import ProtocolModel
from .platform_decision import QualityPolicy


class ExperimentDraft(ProtocolModel):
    name: str = Field(min_length=1, max_length=100)
    suite_id: UUID
    baseline_agent_id: UUID
    candidate_agent_id: UUID
    mode: Literal['controlled', 'benchmark'] = 'benchmark'
    changed_fields: list[str] = Field(default_factory=list, max_length=20)
    repetitions: int = Field(default=1, ge=1, le=5, strict=True)
    timeout_seconds: int = Field(default=600, ge=1, le=3600, strict=True)
    order: Literal['baseline_first', 'candidate_first'] = 'baseline_first'
    intervention: Literal['adapter_default'] = 'adapter_default'
    decision_policy: QualityPolicy | None = None

    @model_serializer(mode='wrap')
    def preserve_legacy_hash(self, handler):
        result = handler(self)
        if self.decision_policy is None:
            result.pop('decision_policy', None)
        return result

    @model_validator(mode='after')
    def validate_fields(self):
        if len(set(self.changed_fields)) != len(self.changed_fields):
            raise ValueError('Duplicate change declarations')
        return self


class ExperimentStart(ExperimentDraft):
    request_key: UUID
    preview_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirm_start: Literal[True]
    allow_model: bool = False
