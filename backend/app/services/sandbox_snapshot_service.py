from dataclasses import dataclass
from pathlib import Path

from ..services.repository_scanner import _is_link_or_reparse_point, discover_python_files
from .repository_scanner import read_file_snapshot
from .workspace_edit_service import resolve_workspace_target

from ..core.exceptions import (
    SandboxPreparationError,
    RepositoryScanError,
    FileSkippedError,
    InvalidWorkspacePathError,
)

MAX_SNAPSHOT_FILES = 500
MAX_SNAPSHOT_FILE_BYTES = 1_000_000
MAX_SNAPSHOT_TOTAL_BYTES = 10_000_000


@dataclass(frozen=True)
class SandboxSnapshot:
    # 复制后的快照目录
    root: Path

    # 实际复制成功的相对路径，统一使用 /
    files: list[str]

    # 实际复制的文件字节数总和
    total_bytes: int


# workspace_path 是仓库工作副本。
# snapshot_path 是调用方创建的空临时目录。
# 从工作区中抽取出一份干净、安全的 Python 代码副本，专门提供给沙箱环境去运行测试。
def prepare_python_test_snapshot(
    workspace_path: Path,
    snapshot_path: Path,
) -> SandboxSnapshot:
    try:
        # 1. 检查两个目录本身不是链接或重解析点。
        if _is_link_or_reparse_point(workspace_path):
            raise SandboxPreparationError("Workspace root must not be a link")

        if _is_link_or_reparse_point(snapshot_path):
            raise SandboxPreparationError("Snapshot root must not be a link")

        # 2. 用 resolve(strict=True) 得到 workspace_root、snapshot_root。
        workspace_root = workspace_path.resolve(strict=True)
        snapshot_root = snapshot_path.resolve(strict=True)

        # 3. 两者都必须是目录。
        if not workspace_root.is_dir() or not snapshot_root.is_dir():
            raise SandboxPreparationError("Workspace and snapshot roots must be directories")

        # 4. snapshot_root 必须为空。
        #    提示：any(snapshot_root.iterdir())
        if any(snapshot_root.iterdir()):
            raise SandboxPreparationError("Snapshot directory must be empty")

        # 5. 两个目录不能相同，也不能互相包含。
        #    提示：Path.is_relative_to()
        if (
            workspace_root == snapshot_root
            or workspace_root.is_relative_to(snapshot_root)
            or snapshot_root.is_relative_to(workspace_root)
        ):
            raise SandboxPreparationError("Workspace and snapshot directories must not overlap")

        # 递归扫描所有有效的 .py 源码文件，并按统一的相对路径规则排序后返回
        paths = discover_python_files(workspace_root)

        # 6. 候选列表为空，抛 SandboxPreparationError。
        if not paths:
            raise SandboxPreparationError("No Python files found")

        # 7. 文件数量超过 MAX_SNAPSHOT_FILES，抛 SandboxPreparationError。
        if len(paths) > MAX_SNAPSHOT_FILES:
            raise SandboxPreparationError("Snapshot file count exceeds the limit")

        copied_files: list[str] = []
        total_bytes = 0

        for candidate in paths:
            relative_path = candidate.relative_to(workspace_root).as_posix()

            # 1. 校验源文件路径，结果保存为 target
            target = resolve_workspace_target(workspace_root, relative_path)

            # 2. 读取源文件，结果保存为 snapshot。
            snapshot = read_file_snapshot(workspace_root, target, max_bytes=MAX_SNAPSHOT_FILE_BYTES)

            # 3. 计算当前文件大小，保存为 file_size。
            file_size = len(snapshot.content)

            # 4. 检查复制后总大小是否超过限制。
            if total_bytes + file_size > MAX_SNAPSHOT_TOTAL_BYTES:
                raise SandboxPreparationError("Snapshot total size exceeds the limit")

            # 5. 用 snapshot_root / relative_path 得到 destination。
            destination = snapshot_root / relative_path

            # 6. 创建 destination 的父目录，然后写入 snapshot.content。
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(snapshot.content)

            # 7. 写成功后，把 relative_path 加入 copied_files。
            #    再把 file_size 加到 total_bytes。
            copied_files.append(relative_path)
            total_bytes += file_size

        return SandboxSnapshot(
            root=snapshot_root,
            files=copied_files,
            total_bytes=total_bytes,
        )

    except (
        RepositoryScanError,
        FileSkippedError,
        InvalidWorkspacePathError,
        OSError,
    ) as exc:
        raise SandboxPreparationError("Cannot prepare Python test snapshot") from exc