# HTTP 边界：校验请求参数、调用业务服务、转换响应和错误；具体读写由 service 完成。
# schemas 定义接口 JSON，db/models 定义数据库表，两者用途不同。
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query

from ...services import retrieval_service
from ...schemas.code_chunk import RepositoryChunkIndexRead, CodeChunkRead, CodeChunkSearchHit
from ...schemas.repository_file import RepositoryFileRead, RepositoryScanRead, SkippedFileRead
from ...core.exceptions import (
    InvalidRepositoryInputError,
    RepositoryInspectionError,
    WorkspaceCreationError,
    RepositoryBusyError,
    RepositoryScanError
)
from ...schemas.repository import RepositoryCreate, RepositoryRead
from ...services import repository_service, repository_indexing_service, code_chunk_service

import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/repositories",
    tags=["repositories"],
)


# 登记源 Git 仓库并创建副本，成功返回 201；不在此接口扫描或分块。
@router.post("", response_model=RepositoryRead, status_code=201)
def create_repository(data: RepositoryCreate):
    try:
        return repository_service.create_repository(data)
    except InvalidRepositoryInputError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except RepositoryInspectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="Repository inspection unavailable"
        ) from exc
    except WorkspaceCreationError as exc:
        raise HTTPException(
            status_code=503,
            detail="Workspace creation unavailable"
        ) from exc


# 返回已有仓库登记信息；只读查询，不访问 Git 或刷新工作副本。
@router.get("/{repository_id}", response_model=RepositoryRead)
def get_repository(repository_id: UUID):
    # 1. 调用 Service 查询
    result = repository_service.get_repository(repository_id)

    # 2. 结果为 None 时，抛出 HTTP 404
    if result is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    # 3. 否则返回结果
    return result

# 查看已入库的文件元数据；仓库不存在返回 404，有仓库但无文件返回 []。
@router.get(
    "/{repository_id}/files",
    response_model=list[RepositoryFileRead],
)
def list_repository_files(repository_id: UUID):
    # 1. 调用 repository_service.list_repository_files。
    result = repository_service.list_repository_files(repository_id=repository_id)

    # 2. 结果为 None 时，抛 HTTP 404
    if result is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    # 3. 否则原样返回列表，包括空列表。
    return result

# 同步工作副本的文件清单，不生成块；锁冲突返回 409，扫描故障返回 503。
@router.post(
    "/{repository_id}/scan",
    response_model=RepositoryScanRead,
)
def scan_repository_files(repository_id: UUID):
    try:
        # 1. 调用同步 Service，保存返回的 scan_result。
        scan_result = repository_indexing_service.sync_repository_files(repository_id=repository_id)

    except RepositoryBusyError as exc:
        # 2. 返回 HTTP 409。
        # 提示信息："Repository is busy"
        raise HTTPException(status_code=409, detail="Repository is busy") from exc

    except RepositoryScanError as exc:
        # 3. 使用 logger.exception 记录失败及 repository_id。
        # 返回 HTTP 503，提示 "Repository scan unavailable"。
        # 不把底层路径和完整异常直接返回给客户端
        logger.exception(
        "Repository scan failed; repository_id=%s",
        repository_id
        )
        raise HTTPException(status_code=503, detail="Repository scan unavailable") from exc

    # 4. scan_result 为 None 时，返回 HTTP 404。
    # 提示信息："Repository not found"
    if scan_result is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    # 5. 将 scan_result.skipped_files 逐个转换为 SkippedFileRead
    skipped_files: list[SkippedFileRead] = []
    for skipped_file in scan_result.skipped_files:
        skipped_files.append(SkippedFileRead.model_validate(skipped_file))

    # 6. 构造并返回 RepositoryScanRead
    return RepositoryScanRead(
        repository_id=repository_id,
        file_count=len(scan_result.files),
        skipped_files=skipped_files,
    )

# 同步执行扫描、分块和入库，无需先调用 /scan；事务提交成功后返回 200 和统计。
# 文件级跳过在响应中列明；整个索引失败才走异常响应。
@router.post(
    "/{repository_id}/index",
    response_model=RepositoryChunkIndexRead,
)
def index_repository(repository_id: UUID):
    try:
        # 1. 调用 repository_indexing_service.index_repository_chunks。
        # 保存返回结果 result。
        result = repository_indexing_service.index_repository_chunks(repository_id=repository_id)

    except RepositoryBusyError as exc:
        # 2. 转换为 HTTP 409，提示 "Repository is busy"。
        raise HTTPException(status_code=409, detail="Repository is busy") from exc

    except RepositoryScanError as exc:
        # 3. 用 logger.exception 记录失败及 repository_id。
        # 转换为 HTTP 503，提示 "Repository indexing unavailable"。
        logger.exception(
        "Repository indexing failed; repository_id=%s", repository_id
        )
        raise HTTPException(status_code=503, detail="Repository indexing unavailable") from exc

    # 4. result 为 None，返回 HTTP 404。
    if result is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    # 5. 参考 /scan 接口：
    # 将 result.skipped_files 逐个转换为 SkippedFileRead。
    skipped_files: list[SkippedFileRead] = []
    for skipped_file in result.skipped_files:
        skipped_files.append(SkippedFileRead.model_validate(skipped_file))

    # 6. 创建并返回 RepositoryChunkIndexRead。
    # repository_id、file_count、chunk_count 来自 result。
    # skipped_files 使用转换后的列表。
    return RepositoryChunkIndexRead(
        repository_id=repository_id,
        file_count=result.file_count,
        chunk_count=result.chunk_count,
        skipped_files=skipped_files,
    )

# 查询已入库代码块，支持相对文件路径精确筛选和分页；不会触发重新索引。
# Query 约束在 HTTP 层将非法分页参数转为 422，服务层负责区分不存在和空结果。
@router.get(
    "/{repository_id}/chunks",
    response_model=list[CodeChunkRead],
)
def list_repository_chunks(
    repository_id: UUID,
    file_path: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    # 1. 调用 code_chunk_service.list_repository_chunks
    result = code_chunk_service.list_repository_chunks(
        repository_id,
        file_path=file_path,
        limit=limit,
        offset=offset
    )

    # 2. 结果为 None 时，抛 HTTP 404。
    # 注意不能使用 if not result，否则会把空列表误判成不存在。
    if result is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    # 3. 返回查询结果。
    return result

@router.get(
    "/{repository_id}/search",
    response_model=list[CodeChunkSearchHit],
)
def search_repository(
    repository_id: UUID,
    query: str = Query(min_length=1, max_length=1000),
    top_k: int = Query(default=5, ge=1, le=20),
):
    # 1. query.strip() 为空时，抛 HTTP 422
    if query.strip() == "":
        raise HTTPException(status_code=422, detail="Query cannot be blank")

    try:
        # 2. 调用 retrieval_service.semantic_search。
        # 传入 repository_id、query、top_k。
        result = retrieval_service.semantic_search(repository_id, query=query, top_k=top_k)
    except httpx.HTTPError as exc:
        # 3. 记录失败日志及 repository_id
        # 不向客户端返回完整上游响应。
        logger.exception(repository_id)
        raise HTTPException(status_code=503, detail="Embedding service unavailable")

    # 4. result 为 None，返回 HTTP 404。
    if result is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    # 5. 返回结果，包括合法的空列表。
    return result