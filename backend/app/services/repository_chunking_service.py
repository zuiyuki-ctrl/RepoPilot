from dataclasses import dataclass
from pathlib import Path

from .repository_scanner import FileMetadata, read_file_snapshot
from ..rag.parse import decode_python_source
from ..rag.chunker import CodeChunkDraft, build_code_chunks
from .repository_scanner import discover_python_files, SkippedFile
from ..core.exceptions import FileSkippedError


@dataclass(frozen=True)
class ChunkedFile:
    # 一个有效文件的元数据和待入库块；空文件/只有常量的文件也有效，chunks 可为空。
    metadata: FileMetadata
    chunks: list[CodeChunkDraft]

"""
负责协调以下流程
read_file_snapshot
    ↓
decode_python_source(snapshot.content)
    ↓
build_code_chunks(source, snapshot.metadata.path)
    ↓
返回文件元数据和代码块
"""
# 单文件流水线：读取快照 → 按声明解码 → AST 分块；整个过程不执行源代码。
# 返回内存对象，不写数据库；可跳过的异常由仓库级循环统一收集。
def chunk_repository_file(
    workspace_path: Path,
    file_path: Path,
    *,
    max_bytes: int = 1024 * 1024,
) -> ChunkedFile:
    # 1. 调用 read_file_snapshot，得到 snapshot
    snapshot = read_file_snapshot(workspace_path, file_path, max_bytes=max_bytes)

    # 2. 对 snapshot.content 解码，得到 source。
    source = decode_python_source(snapshot.content)

    # 3. 调用 build_code_chunks，得到 chunks
    chunks = build_code_chunks(source, snapshot.metadata.path)

    # 4. 创建并返回 ChunkedFile
    return ChunkedFile(
        metadata=snapshot.metadata,
        chunks=chunks,
    )

@dataclass
class RepositoryChunkingResult:
    # 全仓库分块结果；files 只含成功解析的文件，失败文件进入 skipped_files。
    files: list[ChunkedFile]
    skipped_files: list[SkippedFile]

# 我们希望不因为一个文件语法错误就丢掉全部结果
# 扫描并解析工作副本；单文件过大、空字节、编码/语法问题只跳过该文件。
# 目录或文件读取故障仍向外抛出，防止把不完整扫描结果当作完整索引入库。
def chunk_repository(
    workspace_path: Path,
    *,
    max_bytes: int = 1024 * 1024,
) -> RepositoryChunkingResult:
    # 1. 校验 max_bytes > 0，否则抛出 ValueError。
    # 即使仓库为空，也应拒绝不合法的参数。
    if max_bytes <= 0:
        raise ValueError('max_bytes must be > 0')

    # 2. 调用 discover_python_files，得到有序候选文件列表。
    file_list = discover_python_files(workspace_path)

    root = workspace_path.resolve(strict=True)

    files: list[ChunkedFile] = []
    skipped_files: list[SkippedFile] = []

    # 3. 遍历候选文件。
    for file_path in file_list:
        relative_path = file_path.relative_to(root).as_posix()

        try:
            # 4. 调用 chunk_repository_file。
            # 传入 root、file_path 和 max_bytes。
            # 把返回的 ChunkedFile 追加到 files。
            files.append(chunk_repository_file(root, file_path, max_bytes=max_bytes))

        except FileSkippedError as exc:
            # 5. 文件过大、包含空字节等已有跳过情况。
            # 创建 SkippedFile 追加到 skipped_files。
            skipped_files.append(SkippedFile(path=relative_path, reason=str(exc)))

        except UnicodeError:
            # 6. 无法按指定编码解码。
            # 记录 SkippedFile，reason="source_decode_error"
            skipped_files.append(SkippedFile(path=relative_path, reason="source_decode_error"))

        except SyntaxError:
            # 7. Python 语法错误，或编码声明存在问题。
            # 记录 SkippedFile，reason="invalid_python_source"。
            skipped_files.append(SkippedFile(path=relative_path, reason="invalid_python_source"))


    # 8. 返回 RepositoryChunkingResult。
    return RepositoryChunkingResult(files=files, skipped_files=skipped_files)
