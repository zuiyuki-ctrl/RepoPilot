import re
from uuid import UUID

from ..core.exceptions import InvalidAnswerCitationError
from ..rag.context import build_answer_context
from ..rag.generation import generate_answer
from .retrieval_service import semantic_search
from ..schemas.qa import QuestionRequest, QuestionResponse


def answer_repository_question(
    repository_id: UUID,
    data: QuestionRequest,
) -> QuestionResponse | None:
    # 1. question 去掉首尾空白；为空时抛 ValueError。
    question = data.question.strip()
    if not question:
        raise ValueError("empty question")

    # 2. 调用 semantic_search。
    # 仓库不存在，即返回 None 时，本函数也返回 None。
    search_result = semantic_search(repository_id, query=question, top_k=data.top_k)
    if search_result is None:
        return None

    # 3. 调用 build_answer_context
    context = build_answer_context(search_result)

    # 4. context.sources 为空时，直接返回 QuestionResponse：
    # answer="当前没有可用的代码证据，请确认仓库已完成索引和向量化，或调整问题。"
    # sources=[]
    # 此时不调用聊天模型。
    if not context.sources:
        return QuestionResponse(
            repository_id=repository_id,
            answer="当前没有可用的代码证据，请确认仓库已完成索引和向量化，或调整问题",
            sources=[]
        )

    # 5. 调用 generate_answer(question, context.text)。
    answer = generate_answer(question, context.text)

    # 6. 提取答案中的引用编号。
    cited_ids = set(re.findall(r"\[(S[0-9]+)\]", answer))

    # 7. 从 context.sources 收集合法编号 allowed_ids。
    # cited_ids 为空，或不是 allowed_ids 的子集时，
    # 抛 InvalidAnswerCitationError
    allowed_ids = {s.source_id for s in context.sources}
    if not cited_ids or not cited_ids.issubset(allowed_ids):
        raise InvalidAnswerCitationError(
            f"Answer contains invalid or missing citations: {cited_ids}"
        )

    # 8. 返回 QuestionResponse：
    # repository_id、answer、sources=context.sources。
    return QuestionResponse(
        repository_id=repository_id,
        answer=answer,
        sources=context.sources,
    )