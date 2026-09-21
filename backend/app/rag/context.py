import json
from dataclasses import dataclass

from ..schemas.code_chunk import CodeChunkSearchHit
from ..schemas.qa import SourceReference


@dataclass
class AnswerContext:
    text: str
    sources: list[SourceReference]


# 把检索结果整理成有编号的证据
def build_answer_context(
    hits: list[CodeChunkSearchHit],
    *,
    max_chars: int = 20000,
) -> AnswerContext:
    # 1. max_chars 必须大于 0，否则抛 ValueError。
    if max_chars <= 0:
        raise ValueError(f"max_chars must be > 0")

    blocks: list[str] = []
    sources: list[SourceReference] = []
    used_chars = 0

    for hit in hits:
        chunk = hit.chunk

        # 2. 根据已经接纳的块数生成编号：
        source_id = f"S{len(sources) + 1}"

        # 3. 创建证据字典，包含：
        # source_id、file_path、symbol_name、
        # start_line、end_line、content。
        # 用 json.dumps(..., ensure_ascii=False) 转成字符串 block
        evidence = {
            "source_id": source_id,
            "file_path": chunk.file_path,
            "symbol_name": chunk.symbol_name,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "content": chunk.content,
        }
        block = json.dumps(evidence, ensure_ascii=False)

        # 4. 计算加入这块后的总字符数。
        # 块之间用两个换行分隔，也要计入长度。
        # 超过 max_chars 时 continue，尝试后续较小的块
        separator_chars = 2 if blocks else 0
        added_chars = len(block) + separator_chars
        if used_chars + added_chars > max_chars:
            continue

        # 5. 接纳 block，更新 used_chars。
        # 创建对应的 SourceReference，追加到 sources。
        blocks.append(block)
        used_chars += added_chars
        sources.append(SourceReference(
            source_id=source_id,
            chunk_id=chunk.id,
            file_path=chunk.file_path,
            symbol_name=chunk.symbol_name,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
        ))

    # 6. 返回 AnswerContext：
    # text 使用 "\n\n".join(blocks)；
    # sources 使用实际接纳的引用列表。
    return AnswerContext(
        text="\n\n".join(blocks),
        sources=sources,
    )