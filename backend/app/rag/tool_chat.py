import httpx

from ..core import config
from ..schemas.tools import SearchCodeArgs, ReadSourceArgs


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "搜索当前仓库代码，可选择 vector、keyword 或 hybrid。"
                "自然语言实现问题优先使用 vector；"
                "有明确符号名、路径片段或代码词时可使用 keyword；"
                "希望同时利用语义与词面线索时可使用 hybrid。"
                "keyword 不是符号精确查询，也不是任意子串搜索。"
            ),
            "parameters": SearchCodeArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_source",
            "description": "根据搜索结果中的文件路径和行号。读取当前仓库源码，每次最多读取 200 行。",
            "parameters": ReadSourceArgs.model_json_schema(),
        },
    },
]
