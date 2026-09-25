import stat
import os
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from dataclasses import dataclass

from ..core.exceptions import InvalidWorkspacePathError, WorkspaceWriteError

import logging

logger = logging.getLogger(__name__)

def _is_link_or_reparse_point(path: Path) -> bool:
    file_stat = path.lstat()
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(
        stat,
        "FILE_ATTRIBUTE_REPARSE_POINT",
        0,
    )

    return (
            stat.S_ISLNK(file_stat.st_mode)
            or bool(attributes & reparse_flag)
    )


# 在只读/受限的工作空间中，安全地将用户传入的相对路径字符串转换为绝对路径，
# 绝对防止路径穿越、软链接越权读取以及各种跨平台的非法文件名注入。
def resolve_workspace_target(
        workspace_path: Path,
        file_path: str,
) -> Path:
    """
    将仓库相对路径安全地转换为 Workspace 内的绝对路径。

    本方法只解析和验证路径，不创建目录，也不写文件。
    """
    # ---------- 1. 检查 Workspace 根目录 ----------

    try:
        # 在 resolve 之前检查原始 workspace_path。
        if _is_link_or_reparse_point(workspace_path):
            raise InvalidWorkspacePathError()

        # strict=True 保证根目录必须真实存在。
        root = workspace_path.resolve(strict=True)

        # root 必须是目录。
        # 普通文件不能作为 Workspace 根目录。
        if not root.is_dir():
            raise InvalidWorkspacePathError(
                "Workspace path must be a directory"
            )

    except InvalidWorkspacePathError:
        # 我们主动抛出的业务异常原样传播。
        raise

    except (OSError, RuntimeError) as exc:
        # OSError：不存在、无权限、磁盘错误等。
        # RuntimeError：某些平台上可能表示符号链接循环。
        raise InvalidWorkspacePathError(
            "Workspace path cannot be accessed"
        ) from exc

    # ---------- 2. 检查 file_path 的基本类型 ----------

    # file_path 必须真的是 str。
    # 不要直接调用 strip，因为非字符串没有 strip 方法。
    if not isinstance(file_path, str):
        raise InvalidWorkspacePathError(
            "File path must be a string"
        )

    # 不允许空字符串或全空白字符串。
    if not file_path or file_path.strip() == "":
        raise InvalidWorkspacePathError(
            "File path cannot be blank"
        )

    # 不允许首尾空白。
    #
    # "app/main.py " 看起来像 app/main.py，
    # 但实际上可能创建另一个文件。
    if file_path != file_path.strip():
        raise InvalidWorkspacePathError(
            "File path cannot contain surrounding whitespace"
        )

    # ---------- 3. 规定统一的路径语法 ----------

    # API 统一要求使用 /。
    # 拒绝反斜杠，避免 Windows 与 Linux 产生不同解释。
    if "\\" in file_path:
        raise InvalidWorkspacePathError(
            "File path must use forward slashes"
        )

    # 冒号既可能表示 Windows 盘符：
    # C:/secret.txt
    #
    # 也可能表示 Windows Alternate Data Stream：
    # file.py:hidden
    if ":" in file_path:
        raise InvalidWorkspacePathError(
            "File path cannot contain ':'"
        )

    # ---------- 4. 同时检查 POSIX 和 Windows 绝对路径 ----------

    posix_path = PurePosixPath(file_path)
    windows_path = PureWindowsPath(file_path)

    # 如果 posix_path 是绝对路径，拒绝。
    if posix_path.is_absolute():
        raise InvalidWorkspacePathError(
            "File path must be relative"
        )

    # Windows 路径不能有 drive 或 root。
    if windows_path.drive or windows_path.root:
        raise InvalidWorkspacePathError(
            "File path must not contain a Windows drive or root"
        )

    # ---------- 5. 检查每一个路径段 ----------

    parts = file_path.split("/")

    # parts 中不能出现：
    # ""
    # "."
    # ".."
    for part in parts:
        if part in {'', '.', '..'}:
            raise InvalidWorkspacePathError(
                "File path contains an invalid path component"
            )

    # ---------- 6. 构造候选路径 ----------

    candidate = root.joinpath(*parts)

    # 用来记录最终目标是否已经存在。
    target_stat = None

    # ---------- 7. 逐层检查现有路径组件 ----------

    current = root

    try:
        for index, part in enumerate(parts):
            current = current / part

            try:
                # 使用 lstat()，不要使用 stat()。
                #
                # stat() 会跟随符号链接；
                # lstat() 检查链接本身。
                current_stat = current.lstat()

            except FileNotFoundError:
                # 当前组件不存在时，后续路径也不可能存在。
                # 新文件或新目录可以在后面的写入阶段创建。
                break

            # 使用 current_stat.st_mode 检查符号链接
            attributes = getattr(
                current_stat,
                "st_file_attributes",
                0,
            )

            reparse_flag = getattr(
                stat,
                "FILE_ATTRIBUTE_REPARSE_POINT",
                0,
            )

            is_link = stat.S_ISLNK(current_stat.st_mode)
            is_reparse_point = bool(attributes & reparse_flag)
            if is_link or is_reparse_point:
                raise InvalidWorkspacePathError(
                    "Workspace target cannot traverse links"
                )

            is_last = index == len(parts) - 1

            # 如果不是最后一个组件，它必须是目录。
            # 如果 app.py 是普通文件，就不能继续向下。
            if not is_last and not stat.S_ISDIR(current_stat.st_mode):
                raise InvalidWorkspacePathError(
                    "Intermediate path component must be a directory"
                )

            if is_last:
                target_stat = current_stat

        # ---------- 8. 解析最终绝对路径 ----------

        # strict=False：
        # 最终文件允许尚不存在。
        resolved_target = candidate.resolve(strict=False)

    except InvalidWorkspacePathError:
        raise

    except (OSError, RuntimeError) as exc:
        raise InvalidWorkspacePathError(
            "Workspace target cannot be resolved"
        ) from exc

    # ---------- 9. 再次检查 Workspace 边界 ----------

    # 最终目标不能等于 Workspace 根目录。
    if resolved_target == root:
        raise InvalidWorkspacePathError(
            "File path must identify a file"
        )

    # resolved_target 必须仍然位于 root 内。
    if not resolved_target.is_relative_to(root):
        raise InvalidWorkspacePathError(
            "File path escapes the workspace"
        )

    # ---------- 10. 检查已经存在的最终目标 ----------

    if target_stat is not None:
        # 已有目标必须是普通文件。
        #
        # 目录、socket、设备文件等都应该拒绝。
        if not stat.S_ISREG(target_stat.st_mode):
            raise InvalidWorkspacePathError(
                "Workspace target must be a regular file"
            )

    return resolved_target


MAX_WORKSPACE_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class WorkspaceWriteResult:
    file_path: str  # 返回调用者传入的仓库相对路径，不返回本机绝对路径。
    created: bool
    bytes_written: int


def write_workspace_file(
        workspace_path: Path,
        *,
        file_path: str,
        content: str,
        max_bytes: int = MAX_WORKSPACE_FILE_BYTES,
) -> WorkspaceWriteResult:
    # 1. 校验 content 必须是 str。
    #    允许空字符串，因为清空文件可能是合法修改。
    if not isinstance(content, str):
        raise WorkspaceWriteError("Content must be a string")

    # 2. 校验 max_bytes 是正整数。
    #    bool 是 int 的子类，需要明确拒绝 bool。
    if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or max_bytes <= 0
    ):
        raise WorkspaceWriteError("max_bytes must be a positive integer")

    # 3. 将 content 编码成 UTF-8 bytes。
    #    编码后的长度不能超过 max_bytes。
    try:
        encoded_content = content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise WorkspaceWriteError(
            "Content cannot be encoded as UTF-8"
        ) from exc

    if len(encoded_content) > max_bytes:
        raise WorkspaceWriteError(
            "Content exceeds the workspace file size limit"
        )

    # 4. 调用 resolve_workspace_target。
    target = resolve_workspace_target(workspace_path, file_path)

    # 5. 本轮不创建父目录。
    #    target.parent 必须已经存在并且是目录。
    if not (target.parent and target.parent.is_dir()):
        raise WorkspaceWriteError("Workspace target parent directory does not exist")

    # 6. 在写入前记录目标是否存在。
    created = not target.exists()

    # 7. 在 target.parent 中创建临时文件。
    #    必须与目标同目录，确保 os.replace 的原子替换语义。
    temporary_path: Path | None = None

    try:
        # 8. 使用 tempfile.NamedTemporaryFile
        with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=".repopilot-",
                suffix=".tmp",
                delete=False
        ) as temp_file:
            # 9. 替换前再次调用 resolve_workspace_target。
            #    返回值必须仍与 target 相等。
            #    用于发现检查期间路径结构发生变化。
            temporary_path = Path(temp_file.name)
            temp_file.write(encoded_content)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        checked_target = resolve_workspace_target(
            workspace_path,
            file_path,
        )

        if checked_target != target:
            raise WorkspaceWriteError(
                "Workspace target changed during write"
            )

        # 10. 调用 os.replace(temporary_path, target)。
        os.replace(temporary_path, target)

    except InvalidWorkspacePathError:
        # 路径安全错误保持原类型。
        raise

    except WorkspaceWriteError:
        raise

    except OSError as exc:
        raise WorkspaceWriteError(
            "Cannot write workspace file"
        ) from exc

    finally:
        # 11. 如果临时文件仍然存在，尝试删除。
        #     清理失败只记录 warning，不能覆盖原始异常。
        #     不使用递归删除。
        if temporary_path is not None:
            try:
                if temporary_path.exists():
                    temporary_path.unlink()
            except OSError:
                logger.warning(
                    "Failed to remove temporary workspace file",
                    exc_info=True,
                )


    # 12. 返回写入摘要。
    return WorkspaceWriteResult(
        file_path=file_path,
        created=created,
        bytes_written=len(encoded_content),
    )
