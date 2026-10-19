"""Durable quota and idempotency. All mutations lock PlatformRun first."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base


class RunModelGrant(Base):
    __tablename__ = 'run_model_grants'
    __table_args__ = (
        CheckConstraint('calls_reserved >= 0 AND known_total_tokens >= 0', name='ck_model_grant_counters'),
        CheckConstraint('(worker_token IS NULL) = (expires_at IS NULL)', name='ck_model_grant_attempt'),
        UniqueConstraint('credential_sha256', name='uq_run_model_grants_credential'),
    )
    run_id: Mapped[UUID] = mapped_column(ForeignKey('platform_runs.id'), primary_key=True)
    config_sha256: Mapped[str] = mapped_column(String(64))
    policy: Mapped[dict] = mapped_column(JSONB)
    calls_reserved: Mapped[int] = mapped_column(Integer, default=0)
    known_total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    worker_token: Mapped[UUID | None] = mapped_column()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_reason: Mapped[str | None] = mapped_column(String(64))
    credential_sha256: Mapped[str | None] = mapped_column(String(64))
    gateway_mode: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelCall(Base):
    __tablename__ = 'model_calls'
    __table_args__ = (
        UniqueConstraint('run_id', 'call_id', name='uq_model_call_idempotency'),
        CheckConstraint("status IN ('reserved','dispatched','succeeded','failed','unknown')", name='ck_model_call_status'),
        # Defence in depth in addition to the common Run row lock.
        Index('uq_model_call_inflight', 'run_id', unique=True,
              postgresql_where=text("status IN ('reserved','dispatched')")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey('run_model_grants.run_id'), index=True)
    call_id: Mapped[str] = mapped_column(String(64))
    worker_token: Mapped[UUID] = mapped_column()
    request_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usage: Mapped[dict | None] = mapped_column(JSONB)
    # Content is a bounded, immutable artifact, not ordinary log/DB payload.
    result_sha256: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    transport: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
