import os
import stat
import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..core.exceptions import RepositoryScanError, FileSkippedError


EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
}


# 识别符号链接及 Windows 重解析点，避免扫描沿链接走出预期目录。
def _is_link_or_reparse_point(path: Path) -> bool:
    file_stat = path.lstat()
    attributes = getattr(file_stat, "st_file_attributes", 0)

    # 1. 判断是否为符号链接
    if stat.S_ISLNK(file_stat.st_mode):
        return True

    # 2. Windows 下，还需要判断是否为重解析点
    if os.name == "nt" and (attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        return True

    # 3. 任一条件成立返回 True，否则返回 False
    return False


# 让目录遍历失败中止扫描，避免把“无法读取”误当成“文件已删除”并清理数据库。
# os.walk 遍历失败时调用这个函数。
# 不忽略错误，将异常抛出，由外层统一转换
def _raise_walk_error(error: OSError) -> None:
    raise error

# 递归扫描所有有效的 .py 源码文件，并按统一的相对路径规则排序后返回
# 返回按仓库相对路径排序的普通 .py 文件；排除目录、链接、非 .py 文件静默过滤。
# 按磁盘内容扫描，不读取 Git tracked 清单或通用 .gitignore 规则；不写数据库。
def discover_python_files(workspace_path: Path) -> list[Path]:
    try:
        # 1. 检查传入的根路径本身是否为链接或重解析点
        # 如果是，抛 RepositoryScanError
        if _is_link_or_reparse_point(workspace_path):
            raise RepositoryScanError()

        root = workspace_path.resolve(strict=True)

        # 2. 确认 root 是目录，否则抛 RepositoryScanError
        if not root.is_dir():
            raise RepositoryScanError()

        files: list[Path] = []

        for current_dir, dirnames, filenames in os.walk(
            root,
            topdown=True,
            followlinks=False,
            onerror=_raise_walk_error,
        ):
            current_path = Path(current_dir)

            # 3. 筛选可以进入的子目录
            # - 名称不在 EXCLUDED_DIRS 中
            # - 不是链接或重解析点
            allowed_dirs = []

            for dirname in dirnames:
                directory_path = current_path / dirname

                if dirname in EXCLUDED_DIRS:
                    continue

                if _is_link_or_reparse_point(directory_path):
                    continue

                allowed_dirs.append(dirname)

            dirnames[:] = allowed_dirs

            for filename in filenames:
                file_path = current_path / filename

                # 4. 跳过链接或重解析点
                # 提示：continue
                if _is_link_or_reparse_point(file_path):
                    continue

                # 5. 只保留扩展名为 .py 的普通文件
                if file_path.suffix == ".py" and file_path.is_file():
                    # 6. 将符合要求的路径加入 files
                    files.append(file_path)

        # 7. 按仓库相对路径排序后返回
        # 提示：sorted(files, key=...)
        # 排序依据：path.relative_to(root).as_posix()
        def relative_path_key(path: Path) -> str:
            return path.relative_to(root).as_posix()

        return sorted(files, key=relative_path_key)

    except OSError as exc:
        raise RepositoryScanError(
            "Cannot scan workspace files"
        ) from exc

@dataclass(frozen=True)
class FileMetadata:
    # 文件描述信息：相对路径、语言、字节指纹和字节数，不含源码正文。
    path: str
    language: str
    file_hash: str
    size: int

@dataclass(frozen=True)
class FileSnapshot:
    # 同一次读取的原始字节和元数据；让 hash/size 与用于分块的内容保持一致。
    # 这是内存快照，不是磁盘备份，也不是一张数据库表。
    metadata: FileMetadata
    content: bytes

# 读取单个文件，计算大小和 hash
# 有界读取一个文件，默认最多接受 1 MiB；恰好等于上限允许通过。
# 过大/空字节抛 FileSkippedError；路径或读取故障抛 RepositoryScanError。
def read_file_snapshot(
    workspace_path: Path,
    file_path: Path,
    *,
    max_bytes: int = 1024 * 1024,
) -> FileSnapshot:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")

    try:
        root = workspace_path.resolve(strict=True)

        # 1. 跳过扫描后，文件仍有可能发生变化。
        # 再检查 file_path 是否是链接或重解析点，
        # 如果是，抛 RepositoryScanError。
        if _is_link_or_reparse_point(file_path):
            raise RepositoryScanError("Linked files cannot be indexed")

        target = file_path.resolve(strict=True)

        # 2. 确认 target 位于 root 内，并且是普通 .py 文件。
        # 不符合要求时抛 RepositoryScanError。
        if not (target.is_relative_to(root) and target.is_file() and target.suffix == ".py"):
            raise RepositoryScanError("Expected a Python file inside the workspace")

        # 3. 读取原始字节
        # 3.1. 以二进制模式打开文件。
        with target.open("rb") as file:
            # 最多读取 max_bytes + 1 个字节。
            content = file.read(max_bytes + 1)


        # 3.2. 如果读到的字节数超过 max_bytes，
        #    抛 FileSkippedError，并说明文件超过大小限制。
        content_size = len(content)

        if content_size > max_bytes:
            raise FileSkippedError("file_too_large")

        # 4. 判断是否存在空字节
        if b"\x00" in content:
            raise FileSkippedError("contains_null_byte")

        # 5. 计算 SHA-256 十六进制摘要
        # 根据文件内容计算出的“摘要”
        content_hash = hashlib.sha256(content).hexdigest()

        # 6. 得到仓库内相对路径，统一使用 /
        path = target.relative_to(root).as_posix()

        return FileSnapshot(
            metadata=FileMetadata(
                path=path,
                language="python",
                file_hash=content_hash,
                size=content_size,
            ),
            content=content,
        )

    except OSError as exc:
        raise RepositoryScanError(
            "Cannot read workspace file metadata"
        ) from exc

# 复用快照读取及校验，仅返回元数据；不解码、不校验 Python 语法。
def read_file_metadata(
    workspace_path: Path,
    file_path: Path,
    *,
    max_bytes: int = 1024 * 1024,
) -> FileMetadata:
    # 1. 调用 read_file_snapshot
    result = read_file_snapshot(workspace_path, file_path, max_bytes=max_bytes)

    # 2. 返回读取结果中的 metadata 属性
    return result.metadata

@dataclass(frozen=True)
class SkippedFile:
    # 候选文件未被接受的原因；仅用于本次结果返回，不单独持久化。
    path: str
    reason: str

@dataclass
class ScanResult:
    # 一次磁盘扫描的内存结果：有效文件元数据 + 明确跳过的文件。
    files: list[FileMetadata]
    skipped_files: list[SkippedFile]

# 逐个处理，汇总成功文件与跳过原因
# 汇总文件元数据与跳过原因，不写数据库，也不生成代码块。
# 语法错误文件可能通过此扫描；语法检查在后续 chunk_repository 中执行。
def scan_repository(
    workspace_path: Path,
    *,
    max_bytes: int = 1024 * 1024,
) -> ScanResult:
    # 1. 先校验 max_bytes > 0，否则抛 ValueError。
    if max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")

    # 2. 调用 discover_python_files，取得有序候选文件列表。
    # 根路径的有效性检查继续由它负责
    candidate_paths = discover_python_files(workspace_path)

    root = workspace_path.resolve(strict=True)

    files: list[FileMetadata] = []
    skipped_files: list[SkippedFile] = []

    # 3. 遍历候选文件。
    for file_path in candidate_paths:
        try:
            # 调用 read_file_metadata，传入 max_bytes
            # 将返回结果加入 files
            files.append(read_file_metadata(root, file_path, max_bytes=max_bytes))
        except FileSkippedError as exc:
            # 创建 SkippedFile 并加入 skipped_files
            # path 使用仓库相对路径，分隔符为 /
            # reason 使用 str(exc)
            path = file_path.relative_to(root).as_posix()
            skipped_files.append(
                SkippedFile(
                    path=path,
                    reason=str(exc)
                )
            )

    # 4. 返回 ScanResult，传入两个列表。
    return ScanResult(files=files, skipped_files=skipped_files)
