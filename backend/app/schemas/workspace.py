from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# diff 响应模型
class TaskWorkspaceDiffRead(BaseModel):
    task_id: UUID

    repository_id: UUID

    # #　已跟踪文件相对于 HEAD 的文本差异
    diff: str

    changed_files: list[str]

    # 新文件路径，暂不包含其正文
    untracked_files: list[str]

    # Diff 正文是否因字符上限截断
    truncated: bool

class TaskWorkspaceWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    file_path: str = Field(min_length=1)
    content: str

class TaskWorkspaceWriteRead(BaseModel):
    task_id: UUID
    file_path: str
    created: bool
    bytes_written: int = Field(ge=0)
