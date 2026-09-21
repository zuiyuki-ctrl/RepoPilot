from uuid import UUID

from ..schemas.tools import SearchCodeArgs, ReadSourceArgs
from .retrieval_service import semantic_search
from .source_service import read_repository_source


def execute_readonly_tool(
    repository_id: UUID,
    *,
    tool_name: str,
    arguments: dict,
) -> dict:
    if tool_name == "search_code":
        # 1. SearchCodeArgs.model_validate(arguments) 校验参数。
        search_model = SearchCodeArgs.model_validate(arguments)

        # 2. 调用 semantic_search，传入校验后的 query、top_k。
        # 返回 None 时抛 ValueError("Repository not found")。
        hits = semantic_search(repository_id, query=search_model.query, top_k=search_model.top_k)
        if hits is None:
            raise ValueError("Repository not found")

        # 3. 返回 {"hits": [...]}。
        # 每条结果使用 hit.model_dump(mode="json")。
        return {
            "hits": [hit.model_dump(mode="json") for hit in hits],
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