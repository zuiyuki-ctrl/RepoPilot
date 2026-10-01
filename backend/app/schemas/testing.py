from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskTestRead(BaseModel):
    task_id: UUID
    passed: bool
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool


class TestExecutionEventPayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    step_id: str
    attempt: int = Field(ge=1)
    passed: bool
    exit_code: int | None
    timed_out: bool
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool

    # append_task_event 自动加入的公共字段。
    sequence: int = Field(ge=1)
    schema_version: int = Field(ge=1)

    test_run_id: str | None = None