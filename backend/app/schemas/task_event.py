from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TaskEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    sequence: int
    event_type: str
    node_name: str
    message: str
    payload: dict[str, Any]
    created_at: datetime