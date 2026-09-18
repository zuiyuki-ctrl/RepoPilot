import ast
from dataclasses import dataclass

import io
import tokenize

@dataclass(frozen=True)
class ParsedSymbol:
    # AST 解析出的符号位置，尚不包含源码正文，也不是数据库模型。
    symbol_name: str
    symbol_type: str
    start_line: int
    end_line: int


# 解析源码而不执行源码；只检查模块顶层，按出现顺序返回函数/类的位置。
# 顶层变量、import、条件语句内的定义不生成符号；语法错误交给调用方处理。
def parse_top_level_symbols(
    source: str,
    file_path: str,
) -> list[ParsedSymbol]:
    # 1. 将源码解析为 AST。
    # 提示：tree = ast.parse(source, filename=file_path)
    # 本次让 SyntaxError 原样向上传播，不返回空列表。
    tree = ast.parse(source, filename=file_path)

    symbols: list[ParsedSymbol] = []

    # 2. 遍历 tree.body。
    # 它是模块最外层语句的列表
    for node in tree.body:
        # 3.1. 如果是普通函数或异步函数：
        # 将 symbol_type 设置为 "function"。
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbol_type = "function"

        # 3.2. 如果是类：
        # 提示：类节点的类型是 ast.ClassDef。
        # 将 symbol_type 设置为 "class"。
        elif isinstance(node, ast.ClassDef):
            symbol_type = "class"

        # 3.3. 其他语句跳过。
        else:
            continue

        # 4. 从函数节点取得：
        # 名称：node.name
        # 开始行：node.lineno
        # 结束行：node.end_lineno
        name = node.name

        # 默认从 def / async def 所在行开始。
        lineno = node.lineno

        # 4.1. 遍历 node.decorator_list。
        for decorator in node.decorator_list:
            # 4.2. 比较 decorator.lineno 和当前 lineno
            # 将较小的那个保存回 lineno
            lineno = min(decorator.lineno, lineno)

        end_lineno = node.end_lineno
        if end_lineno is None:
            raise ValueError("end_lineno is None")

        # 5. 创建 ParsedSymbol，追加到 symbols
        symbols.append(ParsedSymbol(
            symbol_name=name,
            symbol_type=symbol_type,
            start_line=lineno,
            end_line=end_lineno,
        ))

    # 6. 循环结束后返回 symbols
    return symbols

# 按符号的闭区间行号截取正文，保留原换行符；非法行号抛 ValueError。
def extract_symbol_source(
    source: str,
    symbol: ParsedSymbol,
) -> str:
    # 1. 将源码拆成行，同时保留每行原有的换行符
    source_lines = source.splitlines(keepends=True)

    # 2. 检查行号是否合法：
    # 1 <= symbol.start_line <= symbol.end_line <= len(lines)
    # 不合法时抛出 ValueError，并提供明确的错误信息。
    if not (1 <= symbol.start_line <= symbol.end_line <= len(source_lines)):
        raise ValueError("Invalid symbol line range")

    # 3. 根据开始行和结束行，切出对应的行列表
    line_list = source_lines[symbol.start_line - 1:symbol.end_line]

    # 4. 使用 "".join(...) 将这些行拼回字符串并返回。
    return "".join(line_list)

# 按 Python 编码声明/BOM 解码原始字节；编码或解码失败由分块服务记录为跳过。
def decode_python_source(content: bytes) -> str:
    # 1. 把 content 包装成内存中的二进制流
    # 让内存中的字节拥有类似文件的读取接口
    stream = io.BytesIO(content)

    # 2. 检测 Python 源码编码
    encoding, _ = tokenize.detect_encoding(stream.readline)

    # 3. 使用检测出的 encoding，解码完整的 content 并返回
    return content.decode(encoding)
