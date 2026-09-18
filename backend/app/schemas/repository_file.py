from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# GET /files 的单条响应：文件元数据，不含源码正文或代码块。
class RepositoryFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repository_id: UUID

    # path 是工作区相对路径；size 是字节数；file_hash 是原始字节的 SHA-256。
    path: str
    language: str
    file_hash: str
    size: int
    created_at: datetime
    updated_at: datetime

class SkippedFileRead(BaseModel):
    # 本次处理跳过的文件及原因；排除目录、非 .py 文件等静默过滤项不出现在这里。
    model_config = ConfigDict(from_attributes=True)

    # 1. 文件的仓库相对路径：str
    path: str

    # 2. 跳过原因：str
    reason: str


class RepositoryScanRead(BaseModel):
    # /scan 的结果摘要；file_count 为本次接受的文件数，不代表块数或新增文件数。
    # 1. 本次扫描的仓库 ID：UUID
    repository_id: UUID

    # 2. 成功保存的文件总数：int
    # 字段名：file_count
    # 提示：Field(ge=0)
    file_count: int = Field(ge=0)

    # 3. 跳过文件的明细列表
    # 字段名：skipped_files
    # 类型：list[SkippedFileRead]
    skipped_files: list[SkippedFileRead]
