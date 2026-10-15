from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base


class AgentVersion(Base):
    __tablename__ = 'agent_versions'
    __table_args__ = (UniqueConstraint('name', 'version', name='uq_agent_version_label'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(100))
    content_sha256: Mapped[str] = mapped_column(String(64))
    descriptor: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), default='registered')
    validation: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BenchmarkVersion(Base):
    __tablename__ = 'benchmark_versions'
    __table_args__ = (UniqueConstraint('name', 'version', name='uq_benchmark_version_label'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(100))
    content_sha256: Mapped[str] = mapped_column(String(64))
    descriptor: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), default='registered')
    validation: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CatalogValidation(Base):
    __tablename__ = 'catalog_validations'
    __table_args__ = (
        CheckConstraint('(agent_version_id IS NOT NULL) <> (benchmark_version_id IS NOT NULL)', name='ck_catalog_validation_owner'),
        CheckConstraint("status IN ('queued','running','passed','failed','interrupted')", name='ck_catalog_validation_status'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    request_key: Mapped[UUID] = mapped_column(unique=True)
    agent_version_id: Mapped[UUID | None] = mapped_column(ForeignKey('agent_versions.id'), index=True)
    benchmark_version_id: Mapped[UUID | None] = mapped_column(ForeignKey('benchmark_versions.id'), index=True)
    status: Mapped[str] = mapped_column(String(32), default='queued')
    active_token: Mapped[UUID | None] = mapped_column(unique=True)
    report: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
