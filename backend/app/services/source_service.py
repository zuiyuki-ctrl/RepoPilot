from pathlib import Path
from uuid import UUID

from .repository_service import get_repository
from .repository_scanner import read_file_snapshot
from ..rag.parse import decode_python_source
from ..schemas.source import SourceRead


# 实现读取服务
def read_repository_source(
    repository_id: UUID,
    *,
    file_path: str,
    start_line: int = 1,
    end_line: int = 100,
) -> SourceRead | None:
    # 1. 校验：
    # file_path 不是空白；
    # 1 <= start_line <= end_line；
    # 一次最多请求 200 行，即 end_line - start_line + 1 <= 200。
    # 不符合时抛带说明的 ValueError。
    if file_path.strip() == "":
        raise ValueError("file_path cannot be empty")

    if not 1 <= start_line <= end_line:
        raise ValueError("invalid start_line and end_line")

    if end_line - start_line + 1 > 200:
        raise ValueError("At most 200 lines can be requested")

    # 2. 只接受普通仓库相对路径：
    # 拒绝 relative_path.anchor 非空的路径；
    # 拒绝 ".." 出现在 relative_path.parts 中；
    # Windows 下还应拒绝 ":" 出现在 file_path 中。
    #
    # anchor 可识别盘符、根路径等；
    # ":" 检查同时排除 Windows 的备用数据流写法。
    if ":" in file_path:
        raise ValueError("file_path cannot contain ':'")

    relative_path = Path(file_path)

    # 如果一个路径是纯相对路径，它的 anchor 必定是空字符串 ""
    if relative_path.anchor:
        raise ValueError("file_path cannot contain anchor")

    if ".." in relative_path.parts:
        raise ValueError("file_path cannot contain '..'")


    # 3. 查询仓库，不存在返回 None。
    # workspace_path 为空时抛 ValueError，说明没有工作副本。
    repository = get_repository(repository_id)
    if repository is None:
        return None

    if repository.workspace_path is None:
        raise ValueError("workspace_path cannot be None")

    root = Path(repository.workspace_path)

    # 4. 调用 read_file_snapshot(root, root / relative_path)。
    # 复用已有的工作区边界、普通 .py 文件、
    # 链接检查和 1 MiB 文件大小限制。
    snapshot = read_file_snapshot(root, root / relative_path)

    # 5. 调用 decode_python_source(snapshot.content)。
    # 将源码按行拆分并保留换行符：
    # lines = source.splitlines(keepends=True)
    source = decode_python_source(snapshot.content)
    lines = source.splitlines(keepends=True)

    # 6. start_line 超过文件总行数时，抛 ValueError。
    # 第一版空文件也按“没有可读取的行”处理。
    if start_line > len(lines):
        raise ValueError("start_line cannot be greater than the number of lines")

    # 7. 实际结束行不能超过文件末尾。
    # actual_end = min(end_line, len(lines))
    # 用切片提取并拼接内容。
    actual_end = min(end_line, len(lines))
    content = "".join(lines[start_line - 1:actual_end])

    # 8. 返回内容超过 20000 字符时，抛 ValueError：
    # "Requested source is too large; request fewer lines"
    # 行数少也可能包含很长的一行，所以要同时限制字符数。
    if len(content) > 20000:
        raise ValueError("Requested source is too large; request fewer lines")

    # 9. 返回 SourceRead。
    # file_path、file_hash 来自 snapshot.metadata；
    # end_line 使用 actual_end；
    # total_lines 使用 len(lines)。
    return SourceRead(
        repository_id=repository_id,
        file_path=snapshot.metadata.path,
        file_hash=snapshot.metadata.file_hash,
        start_line=start_line,
        end_line=actual_end,
        total_lines=len(lines),
        content=content,
    )