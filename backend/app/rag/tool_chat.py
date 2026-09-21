import httpx

from ..core import config
from ..schemas.tools import SearchCodeArgs, ReadSourceArgs


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "根据自然语言问题搜索当前仓库中的相关代码。",
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