from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, Text, DateTime, func, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class TaskEvent(Base):
    __tablename__ = "task_events"

    __table_args__ = (
        UniqueConstraint("task_id", "sequence"),

        CheckConstraint("sequence >= 1"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4
    )

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_tasks.id"),
    )

    sequence: Mapped[int] = mapped_column(Integer)

    event_type: Mapped[str] = mapped_column(String(64))

    node_name: Mapped[str] = mapped_column(String(64))

    message: Mapped[str] = mapped_column(Text)

    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
