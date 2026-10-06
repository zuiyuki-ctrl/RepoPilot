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

# 按关键词搜索的响应结构
class CodeChunkKeywordSearchHit(BaseModel):
    chunk: CodeChunkRead
    score: float = Field(ge=0)


# 混合检索响应结构
class CodeChunkHybridSearchHit(BaseModel):
    chunk: CodeChunkRead
    rrf_score: float = Field(ge=0)

    vector_rank: int | None = Field(default=None, ge=1)
    keyword_rank: int | None = Field(default=None, ge=1)

    vector_distance: float | None = None
    keyword_score: float | None = Field(default=None, ge=0)


class HybridSearchDiagnostics(BaseModel):
    # 本次向量候选中不同代码块 ID 的数量
    vector_candidate_count: int = Field(ge=0)

    # 本次关键词候选中不同代码块 ID 的数量
    keyword_candidate_count: int = Field(ge=0)

    # 两路候选 ID 的交集数量
    overlap_count: int = Field(ge=0)

    # 最终返回结果中，keyword_rank 非空的条目数量
    final_keyword_hit_count: int = Field(ge=0)


class HybridSearchResult(BaseModel):
    hits: list[CodeChunkHybridSearchHit]
    diagnostics: HybridSearchDiagnostics