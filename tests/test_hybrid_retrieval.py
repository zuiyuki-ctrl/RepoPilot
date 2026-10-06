from uuid import UUID

import pytest

from backend.app.rag.fusion import fuse_search_results
from backend.app.schemas.code_chunk import (
    CodeChunkRead,
    CodeChunkSearchHit,
    CodeChunkKeywordSearchHit,
)


def make_chunk(number: int, file_path: str) -> CodeChunkRead:
    return CodeChunkRead(
        id=UUID(int=number),
        repository_id=UUID(int=100),
        file_id=UUID(int=200 + number),
        file_path=file_path,
        symbol_name=f"function_{number}",
        symbol_type="function",
        content=f"def function_{number}():\n    pass\n",
        start_line=1,
        end_line=2,
    )


def test_fusion_accumulates_and_orders():
    a = make_chunk(1, "a.py")
    b = make_chunk(2, "b.py")
    c = make_chunk(3, "c.py")

    vector_hits = [
        CodeChunkSearchHit(chunk=a, distance=0.1),
        CodeChunkSearchHit(chunk=b, distance=0.2),
    ]
    keyword_hits = [
        CodeChunkKeywordSearchHit(chunk=b, score=0.9),
        CodeChunkKeywordSearchHit(chunk=c, score=0.8),
    ]

    hits = fuse_search_results(
        vector_hits,
        keyword_hits,
        top_k=3,
    )

    assert [hit.chunk.id for hit in hits] == [b.id, a.id, c.id]
    assert hits[0].vector_rank == 2
    assert hits[0].keyword_rank == 1
    assert hits[0].vector_distance == pytest.approx(0.2)
    assert hits[0].keyword_score == pytest.approx(0.9)
    assert hits[0].rrf_score == pytest.approx(1 / 62 + 1 / 61)

    limited = fuse_search_results(
        vector_hits,
        keyword_hits,
        top_k=1,
    )
    assert [hit.chunk.id for hit in limited] == [b.id]


def test_duplicates_only_contribute_once_per_source():
    a = make_chunk(1, "a.py")

    vector_hit = CodeChunkSearchHit(chunk=a, distance=0.1)
    keyword_hit = CodeChunkKeywordSearchHit(chunk=a, score=0.9)

    hits = fuse_search_results(
        [vector_hit, vector_hit],
        [keyword_hit, keyword_hit],
        top_k=5,
    )

    assert len(hits) == 1
    assert hits[0].chunk.id == a.id
    assert hits[0].vector_rank == 1
    assert hits[0].keyword_rank == 1
    assert hits[0].rrf_score == pytest.approx(2 / 61)


def test_empty_sources_return_empty_list():
    assert fuse_search_results([], [], top_k=5) == []


def test_single_source_leaves_other_source_metadata_empty():
    a = make_chunk(1, "a.py")
    vector_hit = CodeChunkSearchHit(chunk=a, distance=0.1)

    hits = fuse_search_results([vector_hit], [], top_k=5)

    assert len(hits) == 1
    assert hits[0].chunk.id == a.id
    assert hits[0].vector_rank == 1
    assert hits[0].vector_distance == pytest.approx(0.1)
    assert hits[0].keyword_rank is None
    assert hits[0].keyword_score is None


def test_equal_scores_are_ordered_by_file_path():
    a = make_chunk(1, "a.py")
    b = make_chunk(2, "b.py")

    hits = fuse_search_results(
        [
            CodeChunkSearchHit(chunk=b, distance=0.1),
            CodeChunkSearchHit(chunk=a, distance=0.2),
        ],
        [
            CodeChunkKeywordSearchHit(chunk=a, score=0.9),
            CodeChunkKeywordSearchHit(chunk=b, score=0.8),
        ],
        top_k=2,
    )

    assert hits[0].rrf_score == pytest.approx(hits[1].rrf_score)
    assert [hit.chunk.file_path for hit in hits] == ["a.py", "b.py"]


@pytest.mark.parametrize("top_k", [0, 21])
def test_invalid_top_k_is_rejected(top_k):
    with pytest.raises(ValueError):
        fuse_search_results([], [], top_k=top_k)
