"""Durable authoring jobs; confirmed Cases live only in benchmark_versions."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base


class CaseDraft(Base):
    __tablename__ = 'case_drafts'
    __table_args__ = (CheckConstraint(
        "status IN ('queued','validating','generating','ready','failed','interrupted','discarded','confirmed')",
        name='ck_case_draft_status'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    request_key: Mapped[UUID] = mapped_column(unique=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    selection: Mapped[dict] = mapped_column(JSONB)
    preview: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), default='queued', index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    active_token: Mapped[UUID | None] = mapped_column(unique=True)
    text: Mapped[dict | None] = mapped_column(JSONB)
    baseline: Mapped[dict | None] = mapped_column(JSONB)
    observation: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[dict | None] = mapped_column(JSONB)
    confirmed_benchmark_id: Mapped[UUID | None] = mapped_column(ForeignKey('benchmark_versions.id'))
    confirmation: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
