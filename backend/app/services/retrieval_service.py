from uuid import UUID

from ..db.repositories.code_chunk_repo import search_code_chunks
from ..rag.embedding import embed_texts
from ..db.session import SessionLocal
from ..schemas.code_chunk import CodeChunkSearchHit, CodeChunkRead
from ..db.repositories.repository_repo import get_repository
from ..core import config

# 问题向量化，再查询数据库
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