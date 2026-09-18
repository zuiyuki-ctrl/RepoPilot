from pathlib import Path
from dataclasses import dataclass

from ..core.exceptions import RepositoryInspectionError
from ..core.exceptions import InvalidRepositoryInputError
import subprocess

@dataclass(frozen=True)
class GitMetadata:
    # 注册时的提交和分支信息；detached HEAD 没有所属分支，git_branch 为 None。
    commit_hash: str
    git_branch: str | None
    
# 当前是哪次提交、哪个分支？工作区干净吗？
# 要求 HEAD 已有提交且工作区干净，确保后续 clone 能复现用户登记的源码版本。
# 输入状态不合要求抛 InvalidRepositoryInputError；Git 执行故障抛检查异常。
# rev-parse --verify "HEAD^{commit}"：取得当前提交
def read_git_metadata(source_path: Path) -> GitMetadata:
    commit_result = _run_git(
        source_path,
        "rev-parse",
        "--verify",
        "HEAD^{commit}",
    )

    # 非零：抛 InvalidRepositoryInputError
    # 提示 "Cannot resolve a committed HEAD"
    # 成功：从 stdout.strip() 取得 commit_hash
    if commit_result.returncode != 0:
        raise InvalidRepositoryInputError("Cannot resolve a committed HEAD")
    commit_hash = commit_result.stdout.strip()

    # symbolic-ref --quiet --short HEAD：取得当前分支
    branch_result = _run_git(
        source_path,
        "symbolic-ref",
        "--quiet",
        "--short",
        "HEAD",
    )

    # 退出码 0：stdout.strip() 是分支名
    # 退出码 1：detached HEAD，git_branch = None
    # 其他：抛 RepositoryInspectionError
    if branch_result.returncode == 0:
        branch = branch_result.stdout.strip()
    elif branch_result.returncode == 1:
        branch = None
    else:
        raise RepositoryInspectionError("Cannot read git branch")

    # status --porcelain=v1 --untracked-files=all --ignore-submodules=none：检查未提交内容
    status_result = _run_git(
        source_path,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )

    # 非零：抛 RepositoryInspectionError
    # stdout 非空：抛 InvalidRepositoryInputError
    # 提示 "Repository must have a clean working tree"
    if status_result.returncode != 0:
        raise RepositoryInspectionError("Cannot inspect Git working tree status")
    elif status_result.stdout != "":
        raise InvalidRepositoryInputError("Repository must have a clean working tree")

    # 返回 GitMetadata
    return GitMetadata(
        commit_hash=commit_hash,
        git_branch=branch
    )

# 这个路径存在吗？是目录吗？
# 校验绝对目录路径并解析为真实路径；返回值供后续 Git 根目录比较使用。
def validate_source_path(source_path: str) -> Path:
    path = Path(source_path)

    # 1. 要求绝对路径，否则抛出 InvalidRepositoryInputError
    if not path.is_absolute():
        raise InvalidRepositoryInputError("Source path must be absolute")

    # 2. 解析真实路径，并要求路径存在
    # 将 FileNotFoundError 转换成 InvalidRepositoryInputError
    try:
        resolve_path = path.resolve(strict=True)
    except FileNotFoundError:
        raise InvalidRepositoryInputError("Source path does not exist")

    # 3. 确认解析后的路径是目录
    if not resolve_path.is_dir():
        raise InvalidRepositoryInputError("Source path must be a directory")

    # 4. 返回解析后的 Path
    return resolve_path

# 它是不是 Git 工作区根目录？
# 确认传入的是 Git 工作区根目录，不能是普通目录或仓库内部子目录。
# Git 因所有权安全检查拒绝访问时也可能返回非零，需在 API 运行用户下排查。
def validate_git_root(source_path: Path) -> None:
    result = _run_git(source_path, "rev-parse", "--show-toplevel")

    # 1. returncode 不为 0：
    #    抛 InvalidRepositoryInputError，
    #    提示 "Cannot inspect the supplied Git working tree"
    if result.returncode != 0:
        raise InvalidRepositoryInputError("Cannot inspect the supplied Git working tree")

    # 2. 将 stdout 中的根目录转换为 Path：
    #    Path(result.stdout.strip()).resolve(strict=True)
    resolved = Path(result.stdout.strip()).resolve(strict=True)

    # 3. 与已经规范化的 source_path 比较：
    #    不相同时抛 InvalidRepositoryInputError，
    #    提示 "Source path must be the Git working tree root"
    if resolved != source_path:
        raise InvalidRepositoryInputError("Source path must be the Git working tree root")

# 在指定源目录执行只读 Git 检查，最多等待 10 秒；非零退出码由业务调用方解释。
# 无法启动或超时统一转成 RepositoryInspectionError，不在这里处理 HTTP 响应。
def _run_git(
    source_path: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(source_path), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RepositoryInspectionError(
            "Git executable was not found"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RepositoryInspectionError(
            "Git inspection timed out"
        ) from exc
    except OSError as exc:
        raise RepositoryInspectionError(
            "Git command could not be started"
        ) from exc
