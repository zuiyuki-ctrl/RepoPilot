from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base


class PlatformExperiment(Base):
    __tablename__ = 'platform_experiments'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    request_key: Mapped[UUID] = mapped_column(unique=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict] = mapped_column(JSONB)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExperimentMember(Base):
    __tablename__ = 'experiment_members'
    __table_args__ = (UniqueConstraint('experiment_id', 'sequence', name='uq_experiment_member_sequence'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    experiment_id: Mapped[UUID] = mapped_column(ForeignKey('platform_experiments.id'), index=True)
    sequence: Mapped[int]
    case_index: Mapped[int]
    repetition: Mapped[int]
    arm: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default='queued')
    active_token: Mapped[UUID | None] = mapped_column(unique=True)
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey('platform_runs.id'), unique=True)
    error_code: Mapped[str | None] = mapped_column(String(100))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
