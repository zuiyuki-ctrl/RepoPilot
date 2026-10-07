from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .run_config import AgentRunConfig
from .task import TaskRead


# 固定实验用例的文件格式；task_type 是实验分类，不是业务 TaskCreate 的任务类型。
class ExperimentCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    case_id: str = Field(min_length=1)
    case_version: str = Field(min_length=1)
    task_type: Literal["bug_fix", "feature"]
    user_request: str = Field(min_length=1, max_length=1000)
    repository_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    editable_files: list[str] = Field(min_length=1)
    protected_test_files: list[str] = Field(min_length=1)
    test_profile: str = Field(min_length=1)

    # 直接检查原路径，禁止规范化掩盖越界片段；这里只声明范围，不负责执行时的测试保护。
    @model_validator(mode="after")
    def validate_file_scope(self):
        for paths in (self.editable_files, self.protected_test_files):
            if len(paths) != len(set(paths)):
                raise ValueError("File lists must not contain duplicate paths")
            for path in paths:
                parts = path.split("/")
                if (
                    path != path.strip()
                    or "\\" in path
                    or ":" in path
                    or "\x00" in path
                    or any(part in ("", ".", "..") or part.casefold() == ".git" for part in parts)
                    or not path.endswith(".py")
                ):
                    raise ValueError(f"Expected an exact repository-relative Python path: {path!r}")
        if set(self.editable_files) & set(self.protected_test_files):
            raise ValueError("Editable files and protected tests must not overlap")
        return self


class ExperimentPreparation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    experiment_id: UUID
    created_at: datetime
    case: ExperimentCase
    run_config: AgentRunConfig
    status: Literal["preparing", "prepared", "error"]
    stage: str
    repository_id: UUID | None = None
    workspace_path: str | None = None
    task_id: UUID | None = None
    protected_test_file_hashes: dict[str, str]
    error_type: str | None = None


class ExperimentPlanInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    experiment_id: UUID
    task_id: UUID
    inspected_at: datetime
    task_status: str
    scope_status: Literal["not_checked", "valid", "invalid"]
    outside_scope_files: list[str] = Field(default_factory=list)
    # 某个时间点的查询快照；数据库任务及事件仍是权威记录。
    task: TaskRead
