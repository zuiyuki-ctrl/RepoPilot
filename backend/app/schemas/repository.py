from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# 创建接口的请求格式，不是数据库表；拒绝未声明字段，路径/Git 状态由 service 校验。
class RepositoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    source_path: str = Field(min_length=1)

# 仓库信息的响应格式；from_attributes 允许从 ORM 对象读取同名属性生成响应。
# 在数据库会话关闭前转换，避免接口层依赖 ORM 会话和延迟读取。
class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    source_path: str
    workspace_path: str | None
    status: str
    git_branch: str | None
    commit_hash: str | None
    language: str
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None
