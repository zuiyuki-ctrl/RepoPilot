from pathlib import Path
from uuid import uuid4

import subprocess
import shutil
import logging
import os
import stat

logger = logging.getLogger(__name__)

from ..core.exceptions import WorkspaceCreationError

# 工作区分配函数
# 在 workspace_root 下分配唯一空目录；根目录不能位于源仓库内，防止副本嵌套。
def allocate_workspace(
    workspace_root: Path,
    source_path: Path,
) -> Path:
    try:
        root = workspace_root.resolve()
        source = source_path.resolve(strict=True)

        # 1. 如果 root 等于 source，或者位于 source 内部，拒绝
        if root == source or root.is_relative_to(source):
            raise WorkspaceCreationError("Workspace root must be outside the source repository")

        # 2. 创建 root，允许它已经存在
        root.mkdir(parents=True, exist_ok=True)

        # 3. 使用 uuid4().hex 生成子目录名
        workspace_path = root / uuid4().hex

        # 4. 创建子目录，不允许复用已有目录
        # 提示：workspace_path.mkdir(exist_ok=False)
        workspace_path.mkdir(exist_ok=False)
    except OSError as exc:
        raise WorkspaceCreationError("Cannot allocate workspace directory") from exc

    # 5. 返回新目录的 Path
    return workspace_path

# 执行 clone/checkout 等 Git 操作并返回去除首尾空白的标准输出，超时为 120 秒。
# 非零退出、启动失败或超时统一转为 WorkspaceCreationError。
def _run_workspace_git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorkspaceCreationError(
            "Workspace Git operation timed out"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise WorkspaceCreationError(
            "Workspace Git operation failed"
        ) from exc
    except OSError as exc:
        raise WorkspaceCreationError(
            "Workspace Git command could not be started"
        ) from exc

    return result.stdout.strip()

# 将源 Git 仓库（source_path）克隆到新建的独立工作区（workspace_path）
# 并检出（Checkout）到指定的 commit_hash 状态
# 将源仓库克隆到预先分配的空目录，检出指定提交并核对 HEAD，创建可追溯副本。
# detached checkout 不跟随源分支的新提交；后续索引不会自动更新这个副本。
# workspace_path 应为 allocate_workspace 返回的新建空目录
def populate_workspace(
    source_path: Path,
    workspace_path: Path,
    commit_hash: str,
) -> None:
    _run_workspace_git(
        "clone",
        "--no-local",
        "--no-checkout",
        "--template=",
        "--",
        str(source_path),
        str(workspace_path),
    )

    # 1. 在 workspace_path 中执行 checkout --detach commit_hash
    _run_workspace_git(
        "-C",
        str(workspace_path),
        "-c",
        "core.hooksPath=/dev/null",
        "checkout",
        "--detach",
        commit_hash
    )

    # 2. 读取副本 HEAD 对应的完整 commit ID
    commit = _run_workspace_git(
        "-C",
        str(workspace_path),
        "rev-parse",
        "--verify",
        "HEAD^{commit}"
    )

    # 3. 如果与 commit_hash 不一致，抛 WorkspaceCreationError
    if commit != commit_hash:
        raise WorkspaceCreationError("Workspace HEAD does not match the requested commit")

# 处理“创建副本失败后，已经写到磁盘上的东西”
# 创建副本失败时清理残留目录；先限制为工作根目录直属子目录且不得与源仓库重叠。
# 这是磁盘删除操作，与数据库事务回滚不同，必须显式调用并校验路径。
def cleanup_workspace(
    workspace_root: Path,
    workspace_path: Path,
    source_path: Path,
) -> None:
    try:
        # 工作根目录
        root = workspace_root.resolve()
        target = workspace_path.resolve()
        source = source_path.resolve()

        # 1. target 必须是 root 的直接子目录
        # 提示：target.parent != root 时拒绝
        if target.parent != root:
            raise WorkspaceCreationError("Workspace must be a direct child of the workspace root")

        # 2. target 不能等于源仓库、位于源仓库内，
        #    也不能是源仓库的祖先目录
        # 不能删除源仓库，也不能删除源仓库里的目录，
        # 更不能删除包含源仓库的祖先目录。
        if target == source or target.is_relative_to(source) or source.is_relative_to(target):
            raise WorkspaceCreationError("Refusing to remove the source repository or overlapping paths")

        # 3. 目录已经不存在，直接返回
        if not target.exists():
            return

        # 4. 通过以上检查后：
        # rmtree 的失败回调：只为目标副本内的 Windows 普通只读文件解除只读并重试。
        def handle_remove_error(func, path, exc_info):
            error = exc_info[1]

            # 只处理 Windows 上删除文件时的权限错误。
            if (
                    os.name != "nt"
                    or not isinstance(error, PermissionError)
                    or func not in (os.unlink, os.remove)
            ):
                raise error

            file_path = Path(path)

            # 不修改符号链接或 Windows 重解析点的属性。
            file_stat = file_path.lstat()
            attributes = getattr(file_stat, "st_file_attributes", 0)

            if (
                    stat.S_ISLNK(file_stat.st_mode)
                    or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                raise error

            resolved_file = file_path.resolve(strict=True)

            # 只允许修改目标副本内部的普通只读文件。
            if (
                    not resolved_file.is_relative_to(target)
                    or not stat.S_ISREG(file_stat.st_mode)
                    or not attributes & stat.FILE_ATTRIBUTE_READONLY
            ):
                raise error

            os.chmod(file_path, stat.S_IWRITE)
            func(path)

        shutil.rmtree(target, onerror=handle_remove_error)

    except OSError as exc:
        raise WorkspaceCreationError(
            "Cannot clean up workspace directory"
        ) from exc

# 组织成功与失败两条流程
# 分配并填充副本，成功返回路径；填充失败则尝试清理，并保留最初的异常原因。
def create_workspace(
    workspace_root: Path,
    source_path: Path,
    commit_hash: str,
) -> Path:
    workspace_path = allocate_workspace(
        workspace_root,
        source_path,
    )

    try:
        populate_workspace(
            source_path,
            workspace_path,
            commit_hash,
        )
    except Exception:
        try:
            cleanup_workspace(
                workspace_root,
                workspace_path,
                source_path,
            )
        except Exception:
            # checkout 失败后，删除又因权限失败，记录清理异常，再用最后的裸 raise 重新抛出原来的创建异常
            logger.exception(
                "Workspace cleanup failed; residual directory: %s",
                workspace_path,
            )

        raise

    return workspace_path
