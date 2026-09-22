# 移动 _prepare_evidence、_finish_answer，可改名为 prepare_evidence、finish_answer
import re
from copy import deepcopy

from .policy import NO_EVIDENCE_ANSWER
from ..core.exceptions import InvalidAnswerCitationError


# 为真正含源码的工具结果分配证据编号，返回副本及来源清单，不修改原工具结果。
# 这里只准备候选证据；通过字符预算检查并实际发给模型后，调用方才接纳它们。
def prepare_evidence(tool_name: str, result: dict, source_count: int) -> tuple[dict, list[dict]]:
    result = deepcopy(result)
    if "error" in result:
        return result, []

    if tool_name == "search_code":
        candidates = [hit["chunk"] for hit in result["hits"]]
    elif tool_name == "read_source":
        candidates = [result]
    else:
        return result, []

    sources = []
    for candidate in candidates:
        if not candidate["content"].strip():
            continue
        source_id = f"S{source_count + len(sources) + 1}"
        candidate["source_id"] = source_id
        sources.append({
            "source_id": source_id,
            "file_path": candidate["file_path"],
            "start_line": candidate["start_line"],
            "end_line": candidate["end_line"],
        })
    return result, sources


# 只返回有已发送证据支持的引用；编号校验保证引用存在，不等于自动验证结论的语义。
# 无证据时覆盖模型猜测；有证据却缺失/伪造引用时显式报错，与普通问答服务一致。
def finish_answer(answer: str, sources: list[dict], tool_trace: list[dict]) -> dict:
    if not sources:
        return {"answer": NO_EVIDENCE_ANSWER, "tool_trace": tool_trace, "sources": []}

    cited_ids = set(re.findall(r"\[(S[0-9]+)\]", answer))
    allowed_ids = {source["source_id"] for source in sources}
    if not cited_ids or not cited_ids.issubset(allowed_ids):
        raise InvalidAnswerCitationError("Answer contains invalid or missing evidence citations")

    # 来源位置由真实工具结果生成，避免展示时依赖模型自行抄写路径和行号。
    cited_sources = [source for source in sources if source["source_id"] in cited_ids]
    references = "\n".join(
        f"[{source['source_id']}] {source['file_path']}:{source['start_line']}-{source['end_line']}"
        for source in cited_sources
    )
    return {
        "answer": f"{answer}\n\n代码依据：\n{references}",
        "tool_trace": tool_trace,
        "sources": cited_sources,
    }
