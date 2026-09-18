from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from .repository_file import SkippedFileRead


class RepositoryChunkIndexRead(BaseModel):
    # /index 的响应摘要；file_count 包含有效但无函数/类的文件，chunk_count 可以为 0。
    # 单文件解析失败会进入 skipped_files，其他文件仍可正常入库并返回成功响应。
    repository_id: UUID

    # 成功处理的文件数量：file_count
    file_count: int = Field(ge=0)

    # 保存的代码块数量
    chunk_count: int = Field(ge=0)

    # 4. 跳过文件列表：list[SkippedFileRead]。
    skipped_files: list[SkippedFileRead]

class CodeChunkRead(BaseModel):
    # GET /chunks 的单条响应：源码正文、函数/类名称及文件位置，便于查看和引用来源。
    # 这是接口数据格式，不负责读文件、解析源码或执行数据库查询。
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repository_id: UUID
    file_id: UUID

    file_path: str
    symbol_name: str
    symbol_type: str
    content: str

    start_line: int
    end_line: int

# 搜索结果的响应结构
class CodeChunkSearchHit(BaseModel):
    chunk: CodeChunkRead
    distance: float