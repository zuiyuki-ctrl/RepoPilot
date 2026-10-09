"""从本次工具结果和消息构造可追溯摘要，不额外检索、不保存源码正文。"""
import hashlib
from copy import deepcopy

from ..core import config
from ..rag.fusion import RRF_RANK_CONSTANT
from ..services.retrieval_service import HYBRID_CANDIDATE_LIMIT


TRACE_VERSION = 1


def text_hash(text: str) -> str:
    """hash 对应 UTF-8 编码的原字符串，不归一化空白或换行。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_reference(chunk: dict) -> dict:
    return {
        "chunk_id": chunk.get("id"),
        "file_id": chunk.get("file_id"),
        "file_path": chunk["file_path"],
        "symbol_name": chunk.get("symbol_name"),
        "start_line": chunk["start_line"],
        "end_line": chunk["end_line"],
        "content_sha256": text_hash(chunk["content"]),
        "content_chars": len(chunk["content"]),
        "source_id": chunk.get("source_id"),
        # read_source 提供整个文件 hash，检索 chunk 不提供，不能凭内容 hash 冒充。
        "file_hash": chunk.get("file_hash"),
    }


def retrieval_summary(repository_id, arguments: dict, result: dict) -> dict:
    """有序结果是工具最终 Top-K，不冒充 Hybrid 融合前的全部候选。"""
    strategy = result["strategy"]
    query = arguments.get("query")
    return {
        "trace_version": TRACE_VERSION,
        "repository_id": str(repository_id),
        "query": query,
        "effective_query": query.strip() if query is not None and strategy != "vector" else query,
        "top_k": arguments.get("top_k", 5),
        "requested_strategy": result["requested_strategy"],
        "retrieval_strategy": strategy,
        "result_scope": "tool_returned_top_k",
        "hits": [
            {
                "rank": rank,
                **chunk_reference(hit["chunk"]),
                **{key: hit[key] for key in (
                    "distance", "score", "rrf_score", "vector_rank", "keyword_rank",
                    "vector_distance", "keyword_score",
                ) if key in hit},
            }
            for rank, hit in enumerate(result["hits"], start=1)
        ],
        "diagnostics": deepcopy(result.get("diagnostics")),
        "retrieval_parameters": {
            "embedding_model": config.EMBEDDING_MODEL if strategy != "keyword" else None,
            "embedding_dimensions": config.EMBEDDING_DIMENSIONS if strategy != "keyword" else None,
            "rrf_rank_constant": RRF_RANK_CONSTANT if strategy == "hybrid" else None,
            "hybrid_candidate_limit": HYBRID_CANDIDATE_LIMIT if strategy == "hybrid" else None,
            # 目前没有持久化索引版本号，显式缺失；chunk ID + hash 标识本次具体内容。
            "index_version": None,
        },
    }


def context_summary(tool_name: str, result: dict, result_text: str) -> dict:
    """摘要严格对应预算处理后的 tool 消息；不把候选证据标成已接纳。"""
    chunks = []
    if "error" not in result:
        if tool_name == "search_code":
            chunks = [hit["chunk"] for hit in result["hits"]]
        elif tool_name == "read_source":
            chunks = [result]
    return {
        "trace_version": TRACE_VERSION,
        "content_sha256": text_hash(result_text),
        "content_chars": len(result_text),
        "has_error": "error" in result,
        "sources": [chunk_reference(chunk) for chunk in chunks],
    }


def model_tool_context(messages: list[dict]) -> list[dict]:
    """模型调用的工具消息清单，按顺序保留重复 ID，以内容 hash 关联准备事件。"""
    return [
        {
            "tool_message_index": index,
            "tool_call_id": message["tool_call_id"],
            "content_sha256": text_hash(message["content"]),
            "content_chars": len(message["content"]),
        }
        for index, message in enumerate(m for m in messages if m.get("role") == "tool")
    ]
