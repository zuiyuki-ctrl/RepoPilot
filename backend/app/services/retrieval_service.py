from uuid import UUID

from ..rag.fusion import fuse_search_results
from ..db.repositories.code_chunk_repo import search_code_chunks, search_code_chunks_by_keyword
from ..rag.embedding import embed_texts
from ..db.session import SessionLocal
from ..db.repositories.repository_repo import get_repository
from ..core import config
from ..schemas.code_chunk import (
    CodeChunkSearchHit, CodeChunkRead, CodeChunkKeywordSearchHit, CodeChunkHybridSearchHit,
    HybridSearchDiagnostics,
    HybridSearchResult,
)

# 问题向量化，再查询数据库
# 检查仓库后向量化用户问题，再检索同仓库同模型的相近代码块，供问答和搜索工具复用。
def semantic_search(
    repository_id: UUID,
    *,
    query: str,
    top_k: int = 5,
) -> list[CodeChunkSearchHit] | None:
    # 1. query.strip() 后不能为空，top_k 必须在 1～20。
    # 不合法时抛 ValueError。
    if not (query.strip() and 1 <= top_k <= 20):
        raise ValueError("query must be not empty, top_k must be between 1 and 20")

    # 2. 用一个短会话检查仓库是否存在。
    # 不存在返回 None，避免为无效仓库调用百炼。
    with SessionLocal() as session:
        if get_repository(session, repository_id=repository_id) is None:
            return None

    # 3. 此时上面的会话已关闭。
    # 调用 embed_texts([query])，取返回列表的第一个向量
    vector = embed_texts([query])

    # 4. 开启查询会话。
    with SessionLocal() as session:
        # 再检查仓库是否存在，处理网络等待期间仓库被删除的情况。
        if get_repository(session, repository_id=repository_id) is None:
            return None

        # 5. 调用 search_code_chunks
        chunks = search_code_chunks(
            session,
            repository_id=repository_id,
            query_vector=vector[0],
            model=config.EMBEDDING_MODEL,
            top_k=top_k,
        )

        # 6. 遍历 (chunk, distance)：
        # 用 CodeChunkRead.model_validate(chunk) 转换代码块，
        # 创建 CodeChunkSearchHit，收集并返回。
        code_chunks : list[CodeChunkSearchHit] = []
        for chunk, distance in chunks:
            code_chunks.append(
                CodeChunkSearchHit(
                    chunk=CodeChunkRead.model_validate(chunk),
                    distance=distance,
                )
            )

    return code_chunks



def keyword_search(
    repository_id: UUID,
    *,
    query: str,
    top_k: int = 5,
) -> list[CodeChunkKeywordSearchHit] | None:
    query = query.strip()

    # 1. 校验 query 长度为 1～1000，top_k 为 1～20
    if not (1 <= len(query) <= 1000 and 1 <= top_k <= 20):
        raise ValueError(
            "query must be between 1 and 1000, "
            "top_k must be between 1 and 20"
        )

    with SessionLocal() as session:
        # 2. 调用 get_repository
        repository = get_repository(
            session,
            repository_id=repository_id,
        )
        if repository is None:
            return None

        # 3. 调用 search_code_chunks_by_keyword
        rows = search_code_chunks_by_keyword(
            session,
            repository_id=repository_id,
            query=query,
            top_k=top_k,
        )

        # 4. 遍历返回的 (chunk, score)。
        #    用 CodeChunkRead.model_validate(chunk) 转换 ORM 对象，
        #    再构造 CodeChunkKeywordSearchHit。
        #    在会话关闭前完成转换，返回列表。
        hits: list[CodeChunkKeywordSearchHit] = []
        for chunk, score in rows:
            hits.append(
                CodeChunkKeywordSearchHit(
                    chunk=CodeChunkRead.model_validate(chunk),
                    score=score,
                )
            )

        return hits


HYBRID_CANDIDATE_LIMIT = 20

def hybrid_search_with_diagnostics(
    repository_id: UUID,
    *,
    query: str,
    top_k: int = 5,
) -> HybridSearchResult | None:
    query = query.strip()

    # 1. 校验 query 长度为 1～1000，top_k 为 1～20。
    #    不合法时抛 ValueError，不能继续调用向量服务。
    if not (1 <= len(query) <= 1000 and 1 <= top_k <= 20):
        raise ValueError("query must be between 1 and 1000, top_k must be between 1 and 20")

    # 2. 先确认仓库存在，避免为无效 ID 调用向量服务。
    with SessionLocal() as session:
        if get_repository(session, repository_id=repository_id) is None:
            return None

    # 网络请求在数据库会话之外执行。
    query_vector = embed_texts([query])[0]

    with SessionLocal() as session:
        # 必须在这个会话的第一次查询之前设置。
        session.connection(
            execution_options={
                "isolation_level": "REPEATABLE READ",
            }
        )

        # 3. 再检查仓库是否存在。
        #    调用 get_repository(session, repository_id=repository_id)。
        #    不存在返回 None，处理网络等待期间仓库被删除的情况。
        repository = get_repository(session, repository_id=repository_id)
        if repository is None:
            return None

        vector_rows = search_code_chunks(
            session,
            repository_id=repository_id,
            query_vector=query_vector,
            model=config.EMBEDDING_MODEL,
            top_k=HYBRID_CANDIDATE_LIMIT,
        )

        keyword_rows = search_code_chunks_by_keyword(
            session,
            repository_id=repository_id,
            query=query,
            top_k=HYBRID_CANDIDATE_LIMIT,
        )

        # 4. 在会话关闭前转换两路结果：
        #
        # vector_rows 中的 (chunk, distance)
        vector_hits = []
        for chunk, distance in vector_rows:
            vector_hits.append(
                CodeChunkSearchHit(
                    chunk=CodeChunkRead.model_validate(chunk),
                    distance=distance,
                )
            )

        # keyword_rows 中的 (chunk, score)
        # 分别保存为 vector_hits 和 keyword_hits。
        keyword_hits = []
        for chunk, score in keyword_rows:
            keyword_hits.append(
                CodeChunkKeywordSearchHit(
                    chunk=CodeChunkRead.model_validate(chunk),
                    score=score,
                )
            )

    final_hits = fuse_search_results(
        vector_hits,
        keyword_hits,
        top_k=top_k,
    )

    vector_ids = {hit.chunk.id for hit in vector_hits}
    keyword_ids = {hit.chunk.id for hit in keyword_hits}

    # 1. HybridSearchDiagnostics。
    final_hits_count = 0
    for hit in final_hits:
        if hit.keyword_rank is not None:
            final_hits_count += 1

    diagnostics = HybridSearchDiagnostics(
        vector_candidate_count=len(vector_ids),
        keyword_candidate_count=len(keyword_ids),
        overlap_count=len(vector_ids & keyword_ids),
        final_keyword_hit_count=final_hits_count,
    )

    return HybridSearchResult(
        hits=final_hits,
        diagnostics=diagnostics,
    )

def hybrid_search(
    repository_id: UUID,
    *,
    query: str,
    top_k: int = 5,
) -> list[CodeChunkHybridSearchHit] | None:
    result = hybrid_search_with_diagnostics(
        repository_id,
        query=query,
        top_k=top_k,
    )

    if result is None:
        return None

    return result.hits