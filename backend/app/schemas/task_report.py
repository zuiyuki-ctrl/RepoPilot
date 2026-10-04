from typing import Literal

from pydantic import BaseModel, Field

from .reflection import ReflectionDecision
from ..schemas.task import TaskRead
from ..schemas.testing import TestRunRead
from ..schemas.workspace import TaskWorkspaceDiffRead


class TaskFailureSummary(BaseModel):
    # 任务表中保存的 task.error
    reason: str

    # 说明这次终止的事件序号
    event_sequence: int = Field(ge=1)

    # 规划执行失败，还是 Reflection 决定停止
    event_type: Literal["TASK_FAILED", "REFLECTION_FINISHED"]

    # 只有 Reflection 决定停止时，返回当时保存的诊断和决定
    reflection: ReflectionDecision | None = None


class TaskExecutionReport(BaseModel):
    task: TaskRead
    completion_event_sequence: int | None = Field(ge=1)
    test_run: TestRunRead | None
    final_diff: TaskWorkspaceDiffRead | None
    failure: TaskFailureSummary | None = None

    diff_scope: Literal["workspace_against_head"] = "workspace_against_head"
