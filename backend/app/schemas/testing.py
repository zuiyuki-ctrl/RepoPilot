from uuid import UUID

from pydantic import BaseModel


class TaskTestRead(BaseModel):
    task_id: UUID
    passed: bool
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool