"""通用 Run 生命周期与证据归属；外部运行不需要伪造 AgentTask。"""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base


class PlatformRun(Base):
    __tablename__ = 'platform_runs'
    __table_args__ = (
        CheckConstraint("lifecycle IN ('queued','preparing','running','awaiting_input','evaluating','finished','interrupted')", name='ck_platform_runs_lifecycle'),
        CheckConstraint("execution_status IN ('pending','completed','failed','timed_out','cancelled','unknown')", name='ck_platform_runs_execution'),
        CheckConstraint("evaluation_outcome IN ('pending','passed','not_passed','unknown')", name='ck_platform_runs_evaluation'),
        CheckConstraint('version >= 1 AND event_sequence >= 0', name='ck_platform_runs_counters'),
        CheckConstraint("(lifecycle IN ('finished','interrupted')) = (completed_at IS NOT NULL)", name='ck_platform_runs_terminal_time'),
        CheckConstraint("evaluation_outcome != 'passed' OR (execution_status = 'completed' AND lifecycle = 'finished')", name='ck_platform_runs_passed'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey('repositories.id'), index=True)
    legacy_task_id: Mapped[UUID | None] = mapped_column(ForeignKey('agent_tasks.id'), unique=True)
    creation_key: Mapped[str] = mapped_column(String(100), unique=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict] = mapped_column(JSONB)
    lifecycle: Mapped[str] = mapped_column(String(32), default='queued')
    execution_status: Mapped[str] = mapped_column(String(32), default='pending')
    evaluation_outcome: Mapped[str] = mapped_column(String(32), default='pending')
    version: Mapped[int] = mapped_column(Integer, default=1)
    event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    capabilities: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformRunEvent(Base):
    __tablename__ = 'platform_run_events'
    __table_args__ = (
        UniqueConstraint('run_id', 'sequence', name='uq_platform_run_events_sequence'),
        CheckConstraint('sequence > 0', name='ck_platform_run_events_sequence'),
        CheckConstraint("source IN ('platform','adapter','agent_reported')", name='ck_platform_run_events_source'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey('platform_runs.id'), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunEvaluation(Base):
    __tablename__ = 'run_evaluations'
    __table_args__ = (
        UniqueConstraint('run_id', 'evidence_sha256', name='uq_run_evaluations_evidence'),
        CheckConstraint("outcome IN ('passed','not_passed','unknown')", name='ck_run_evaluations_outcome'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey('platform_runs.id'), index=True)
    # TestRun 的归属在保存服务中核对；终态证据不覆盖。
    test_run_id: Mapped[UUID | None] = mapped_column(ForeignKey('test_runs.id'))
    evidence_sha256: Mapped[str] = mapped_column(String(64))
    rule_sha256: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(100))
    evidence: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunWork(Base):
    """每个 Run 的可恢复游标；active_token 未清除时任何新 worker 都不得重放。"""
    __tablename__ = 'run_work'
    __table_args__ = (CheckConstraint('active_seconds >= 0', name='ck_run_work_seconds'),)
    run_id: Mapped[UUID] = mapped_column(ForeignKey('platform_runs.id'), primary_key=True)
    stage: Mapped[str] = mapped_column(String(32), default='prepare')
    state: Mapped[dict] = mapped_column(JSONB, default=dict)
    ready: Mapped[bool] = mapped_column(Boolean, default=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    active_token: Mapped[UUID | None] = mapped_column(unique=True)
    active_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_seconds: Mapped[float] = mapped_column(Float, default=0)
    result: Mapped[dict | None] = mapped_column(JSONB)
    cleanup_status: Mapped[str] = mapped_column(String(32), default='not_needed')
    error_code: Mapped[str | None] = mapped_column(String(100))
    legacy_cursor: Mapped[int] = mapped_column(Integer, default=0)


class RunCheckpoint(Base):
    __tablename__ = 'run_checkpoints'
    __table_args__ = (
        CheckConstraint("kind IN ('plan','candidate')", name='ck_run_checkpoint_kind'),
        CheckConstraint("decision IS NULL OR decision IN ('approved','rejected')", name='ck_run_checkpoint_decision'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey('platform_runs.id'), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    run_version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str | None] = mapped_column(String(16))
    comment: Mapped[str | None] = mapped_column(String(1000))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
