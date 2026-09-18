from uuid import UUID

from sqlalchemy.exc import DBAPIError

from ..core import config
from ..core.exceptions import RepositoryBusyError
from ..db.session import SessionLocal
from ..db.repositories.repository_repo import get_repository_for_update
from ..db.repositories.code_chunk_repo import list_chunks_needing_embedding
from ..rag.embedding import embed_texts

# 编写分批保存服务
def embed_repository_chunks(repository_id: UUID) -> int | None:
    model = config.EMBEDDING_MODEL
    embedded_count = 0

    with SessionLocal.begin() as session:
        # 1. 沿用已有仓库加锁逻辑。
        # SQLSTATE 55P03 转换为 RepositoryBusyError；
        # 其他数据库异常继续抛出。
        try:
            repository = get_repository_for_update(session, repository_id)
        except DBAPIError as exc:
            result = getattr(exc.orig, "sqlstate", None)

            if result == "55P03":
                raise RepositoryBusyError("Repository is busy") from exc

            raise

        # 2. 仓库不存在，返回 None。
        if repository is None:
            return None

        while True:
            # 3. 查询当前仓库、当前 model 的一批待处理代码块。
            chunks = list_chunks_needing_embedding(
                session,
                repository_id=repository_id,
                model=model,
            )

            # 4. 没有待处理记录，break。
            if not chunks:
                break

            # 5. 按查询结果顺序，收集每个 chunk.content。
            # 调用 embed_texts，得到 vectors。
            texts : list[str] = []
            for chunk in chunks:
                texts.append(chunk.content)

            vectors = embed_texts(texts)

            # 6. 将代码块和向量逐个配对：
            for chunk, vector in zip(chunks, vectors, strict=True):
                # 设置 chunk.embedding 和 chunk.embedding_model。
                chunk.embedding = vector
                chunk.embedding_model = model

            # 7. flush，让本批修改发送到数据库。
            # 累加本批处理数量。
            session.flush()
            embedded_count += len(chunks)

    # 8. 提交成功后返回 embedded_count。
    return embedded_count