from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Text, String, DateTime, func, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import mapped_column, Mapped

from ..base import Base

class AgentTask(Base):
    __tablename__ = "agent_tasks"

    __table_args__ = (
        CheckConstraint(
            "review_decision IS NULL "
            "OR review_decision IN ('approved', 'rejected')",
            name="ck_agent_tasks_review_decision",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4
    )

    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id"),
    )

    user_request: Mapped[str] = mapped_column(Text)

    task_type: Mapped[str] = mapped_column(
        String(32),
        default="question"
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="created"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # 保存结构化回答 包含 repository_id、answer、tool_trace、sources
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, # 数据库中的 JSON 对象
        nullable=True
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    review_decision: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True
    )

    review_comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )