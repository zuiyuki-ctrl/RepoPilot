from uuid import UUID

from ..schemas.run_config import AgentRunConfig
from ..schemas.tools import SearchCodeArgs, ReadSourceArgs
from .retrieval_service import semantic_search, keyword_search, hybrid_search_with_diagnostics
from .source_service import read_repository_source


# 校验模型给出的工具参数，将 search_code/read_source 分发到现有服务并返回可序列化结果。
# 仓库范围由调用方固定，拒绝未知工具，是 Agent 访问源码的只读入口。
def execute_readonly_tool(
    repository_id: UUID,
    *,
    tool_name: str,
    arguments: dict,
    run_config: AgentRunConfig | None = None,
) -> dict:
    effective_config = (
        run_config if run_config is not None else AgentRunConfig()
    )

    if tool_name == "search_code":
        # 1. SearchCodeArgs.model_validate(arguments) 校验参数。
        search_model = SearchCodeArgs.model_validate(arguments)
        requested_strategy = search_model.strategy
        effective_strategy = effective_config.resolve_retrieval_strategy(
            requested_strategy
        )

        diagnostics = None
        if effective_strategy == "vector":
            hits = semantic_search(repository_id, query=search_model.query, top_k=search_model.top_k)
        elif effective_strategy == "keyword":
            hits = keyword_search(repository_id, query=search_model.query, top_k=search_model.top_k)
        else:
            details = hybrid_search_with_diagnostics(
                repository_id, query=search_model.query, top_k=search_model.top_k,
            )
            if details is None:
                raise ValueError("Repository not found")
            hits = details.hits
            diagnostics = details.diagnostics.model_dump(mode="json")
        if hits is None:
            raise ValueError("Repository not found")

        # 保留各策略原有评分字段，空命中列表是正常结果。
        return {
            "requested_strategy": requested_strategy,
            "strategy": effective_strategy,
            "hits": [hit.model_dump(mode="json") for hit in hits],
            "diagnostics": diagnostics,
        }

    elif tool_name == "read_source":
        # 4. ReadSourceArgs.model_validate(arguments)。
        read_model = ReadSourceArgs.model_validate(arguments)

        # 5. 调用 read_repository_source，传递路径和行号。
        # 返回 None 时抛 ValueError("Repository not found")。
        result = read_repository_source(
            repository_id,
            file_path=read_model.file_path,
            start_line=read_model.start_line,
            end_line=read_model.end_line,
        )
        if result is None:
            raise ValueError("Repository not found")

        # 6. 返回 result.model_dump(mode="json")。
        return result.model_dump(mode="json")

    else:
        # 7. 未知工具名直接拒绝，抛 ValueError。
        raise ValueError("Unknown tool {}".format(tool_name))
