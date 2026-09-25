import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..core.exceptions import (
    InvalidWorkspacePathError,
    WorkspaceDiffError,
)
from .workspace_edit_service import _is_link_or_reparse_point

MAX_WORKSPACE_DIFF_CHARS = 100_000


@dataclass(frozen=True)
class WorkspaceDiffResult:
    #　已跟踪文件相对于 HEAD 的文本差异
    diff: str

    # 已跟踪且发生变化的仓库相对路径
    changed_files: list[str]

    # Git 尚未跟踪的新文件
    untracked_files: list[str]

    # diff 是否因为输出预算而截断
    truncated: bool

# 增加 Git 命令助手
def _run_workspace_git(
    workspace_path: Path,
    *args: str,
) -> str:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(workspace_path),
                *args,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
            env={
                **os.environ,
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
    except subprocess.TimeoutExpired as exc:
        raise WorkspaceDiffError(
            "Workspace Git command timed out"
        ) from exc
    except OSError as exc:
        raise WorkspaceDiffError(
            "Workspace Git command could not be started"
        ) from exc

    if result.returncode != 0:
        raise WorkspaceDiffError(
            "Workspace Git command failed"
        )

    return result.stdout

def read_workspace_diff(
    workspace_path: Path,
    *,
    max_chars: int = MAX_WORKSPACE_DIFF_CHARS,
) -> WorkspaceDiffResult:
    # 1. 校验 max_chars：
    #    必须是非 bool 的正整数。
    ...

    # 2. 严格解析 workspace 根目录：
    #    - 必须存在；
    #    - 不能是符号链接/reparse point；
    #    - 必须是目录；
    #    路径异常转换为 InvalidWorkspacePathError。
    ...

    # 3. 执行 rev-parse --show-toplevel。
    #    将返回路径 resolve(strict=True)。
    #    必须严格等于 workspace 根目录。
    ...

    # 4. 读取已跟踪文件的 diff。
    tracked_diff = _run_workspace_git(
        root,
        "diff",
        "HEAD",
        "--no-ext-diff",
        "--no-textconv",
        "--no-color",
        "--",
    )

    # 5. 读取发生变化的已跟踪文件。
    changed_output = _run_workspace_git(
        root,
        "diff",
        "HEAD",
        "--name-only",
        "-z",
        "--",
    )

    # 6. 读取未跟踪文件。
    untracked_output = _run_workspace_git(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )

    # 7. 将两个 NUL 分隔结果转换为路径列表。
    #    丢弃末尾空字符串，保留 Git 返回顺序。
    changed_files = ...
    untracked_files = ...

    # 8. 根据 max_chars 截断 tracked_diff。
    #    len <= max_chars 时不截断。
    #    超出时只保留前 max_chars 个 Python 字符。
    ...

    # 9. 返回 WorkspaceDiffResult。
    return WorkspaceDiffResult(
        diff=...,
        changed_files=changed_files,
        untracked_files=untracked_files,
        truncated=...,
    )