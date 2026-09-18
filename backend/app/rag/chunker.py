from dataclasses import dataclass

from .parse import parse_top_level_symbols, extract_symbol_source

# 表示“尚未入库的代码块”。暂时没有数据库 ID、外键或向量，它只描述代码本身
@dataclass(frozen=True)
class CodeChunkDraft:
    # 内存中的待入库块：位置 + 名称 + 正文，没有数据库 ID、外键或向量。
    # 后续 save_chunked_file 会给它补上仓库/文件归属，写入 CodeChunk 表。
    file_path: str
    symbol_name: str
    symbol_type: str
    start_line: int
    end_line: int
    content: str

# 一整个函数或类对应一个代码块
# 将 AST 符号和对应源码片段组装为块；合法文件没有函数/类时返回空列表。
# 当前按完整顶层符号分块，不按固定字符数/token 数切分，也不写数据库。
def build_code_chunks(
    source: str,
    file_path: str,
) -> list[CodeChunkDraft]:
    # 1. 调用 parse_top_level_symbols，取得符号列表。
    symbol_list = parse_top_level_symbols(source, file_path)

    chunks: list[CodeChunkDraft] = []

    # 2. 遍历符号列表。
    # 对每个 symbol：
    #   a. 调用 extract_symbol_source(source, symbol)。
    #   b. 创建 CodeChunkDraft：
    #      file_path 使用本函数参数；
    #      名称、类型和行号来自 symbol；
    #      content 使用刚提取的源码。
    #   c. 追加到 chunks。
    for symbol in symbol_list:
        content = extract_symbol_source(source, symbol)
        chunks.append(CodeChunkDraft(
            file_path=file_path,
            symbol_name=symbol.symbol_name,
            symbol_type=symbol.symbol_type,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            content=content,
        ))

    # 3. 循环结束后返回 chunks。
    return chunks
