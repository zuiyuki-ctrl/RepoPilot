import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, DateTime, Integer, Boolean, Text, false, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...db.base import Base


class TestRun(Base):
    __tablename__ = "test_runs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'finished', 'error')",
            name="ck_test_runs_status"
        ),
        CheckConstraint(
            "timeout_seconds > 0",
            name="ck_test_runs_timeout_positive"
        ),
        CheckConstraint(
            "(status = 'running' AND completed_at IS NULL)"
            "OR"
            "(status IN ('finished', 'error') AND completed_at IS NOT NULL)",
            name="ck_test_runs_completion"
        )
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4
    )

    task_id : Mapped[UUID] = mapped_column(
        ForeignKey("agent_tasks.id"),
        nullable=False,
        index=True
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    image: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    exit_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    timed_out : Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false()
    )

    stdout: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    stderr: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    stdout_truncated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    stderr_truncated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    snapshot_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
