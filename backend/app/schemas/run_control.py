from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import ConfigDict, Field
from .platform_run import Hash, ProtocolModel


class ApprovalRequest(ProtocolModel):
    expected_version: int = Field(ge=1, strict=True)
    payload_sha256: Hash
    decision: Literal['approved', 'rejected']
    comment: str = Field(default='', max_length=1000)


class CancelRequest(ProtocolModel):
    expected_version: int = Field(ge=1, strict=True)


class CheckpointRead(ProtocolModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)
    id: UUID
    run_id: UUID
    kind: Literal['plan', 'candidate']
    run_version: int
    payload: dict
    payload_sha256: str
    decision: str | None
    comment: str | None
    decided_at: datetime | None


class ControlRead(ProtocolModel):
    stage: str
    ready: bool
    active: bool
    cancel_requested: bool
    cleanup_status: str
    error_code: str | None
    active_seconds: float
    interruption_token: UUID | None = None
    cleanup_error_code: str | None = None
    checkpoint: CheckpointRead | None = None
