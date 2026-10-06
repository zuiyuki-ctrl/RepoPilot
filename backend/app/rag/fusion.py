from uuid import UUID

from ..schemas.code_chunk import (
    CodeChunkSearchHit,
    CodeChunkKeywordSearchHit,
    CodeChunkHybridSearchHit,
)


RRF_RANK_CONSTANT = 60

# 纯排名融合函数
def fuse_search_results(
    vector_hits: list[CodeChunkSearchHit],
    keyword_hits: list[CodeChunkKeywordSearchHit],
    *,
    top_k: int = 5,
) -> list[CodeChunkHybridSearchHit]:
    # 1. 校验 1 <= top_k <= 20，不合法时抛 ValueError。
    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20")

    merged: dict[UUID, CodeChunkHybridSearchHit] = {}

    # 2. 记录向量排名，并计算这一份排名的贡献。
    for rank, hit in enumerate(vector_hits, start=1):
        chunk_id = hit.chunk.id

        if chunk_id not in merged:
            merged[chunk_id] = CodeChunkHybridSearchHit(
                chunk=hit.chunk,
                rrf_score=0.0,
            )

        item = merged[chunk_id]

        # 同一路重复的 ID 只采用第一次出现的排名。
        if item.vector_rank is not None:
            continue

        item.vector_rank = rank
        item.vector_distance = hit.distance
        item.rrf_score += 1.0 / (RRF_RANK_CONSTANT + rank)

    # 3. 遍历 keyword_hits，同样从 1 开始编号。
    #    记录 keyword_rank、keyword_score。
    #    在已有 rrf_score 上累加本路贡献，不要覆盖向量贡献。
    for rank, hit in enumerate(keyword_hits, start=1):
        chunk_id = hit.chunk.id

        if chunk_id not in merged:
            merged[chunk_id] = CodeChunkHybridSearchHit(
                chunk=hit.chunk,
                rrf_score=0.0,
            )

        item = merged[chunk_id]
        if item.keyword_rank is not None:
            continue

        item.keyword_rank = rank
        item.keyword_score = hit.score
        item.rrf_score += 1.0 / (RRF_RANK_CONSTANT + rank)

    # 4. 对 merged 排序：
    #    第一关键字：-item.rrf_score
    #    第二关键字：item.chunk.file_path
    #    第三关键字：item.chunk.start_line
    #    第四关键字：str(item.chunk.id)
    ranked_hits = sorted(
        merged.values(),
        key=lambda _item: (
            -_item.rrf_score,
            _item.chunk.file_path,
            _item.chunk.start_line,
            str(_item.chunk.id)
        )
    )

    # 5. 排序后截取前 top_k 条。
    #    两路都是空列表时，自然返回 []。
    return ranked_hits[:top_k]