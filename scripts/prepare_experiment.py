import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from backend.app.core.exceptions import (
    FileSkippedError, InvalidWorkspacePathError, RepositoryInspectionError, RepositoryScanError,
)
from backend.app.core.test_profiles import get_test_profile
from backend.app.schemas.experiment import ExperimentCase
from backend.app.services import repository_source
from backend.app.services.repository_scanner import read_file_snapshot
from backend.app.services.workspace_edit_service import resolve_workspace_target


def load_experiment_case(path: Path) -> ExperimentCase:
    """读取一个固定用例文件并完成结构校验。"""
    return ExperimentCase.model_validate_json(path.read_text(encoding="utf-8"))


# 精确查询 Git 索引，拒绝只存在于本机的忽略文件；不把路径当作通配表达式。
def require_tracked_file(root: Path, *, file_path: str) -> None:
    result = repository_source._run_git(
        root, "--literal-pathspecs", "ls-files", "--error-unmatch", "--", file_path,
    )
    if result.returncode == 1:
        raise ValueError(f"Experiment file must be tracked by Git: {file_path}")
    if result.returncode != 0:
        raise RepositoryInspectionError(f"Cannot inspect Git tracking for: {file_path}")


# 仅检查固定提交、环境配置名称和现存文件；不注册仓库、不检查镜像、不创建实验运行。
def inspect_experiment_source(case: ExperimentCase, *, source_path: Path) -> dict:
    """确认本机源仓库对应固定用例，返回准备摘要。"""
    root = repository_source.validate_source_path(str(source_path))
    repository_source.validate_git_root(root)
    metadata = repository_source.read_git_metadata(root)
    if metadata.commit_hash != case.repository_commit:
        raise ValueError(f"Repository commit mismatch: expected {case.repository_commit}, got {metadata.commit_hash}")
    try:
        profile = get_test_profile(case.test_profile)
    except ValueError as exc:
        raise ValueError(f"Unknown test profile: {case.test_profile}") from exc

    protected_hashes = {}
    for file_path in case.editable_files + case.protected_test_files:
        require_tracked_file(root, file_path=file_path)
        target = resolve_workspace_target(root, file_path)
        snapshot = read_file_snapshot(root, target)
        if file_path in case.protected_test_files:
            protected_hashes[file_path] = snapshot.metadata.file_hash

    return {
        "case_id": case.case_id,
        "case_version": case.case_version,
        "repository_commit": metadata.commit_hash,
        "source_path": str(root),
        "editable_files": case.editable_files,
        "protected_test_file_hashes": protected_hashes,
        "test_profile": profile.name,
        "image": profile.image,
    }


# 检查通过只代表当前准备状态；后续注册仍需核对提交，执行入口仍需强制限制修改范围。
def main() -> None:
    parser = argparse.ArgumentParser(description="只读检查固定实验用例与本机源仓库")
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--source-path", required=True, type=Path)
    args = parser.parse_args()
    try:
        case = load_experiment_case(args.case)
        summary = inspect_experiment_source(case, source_path=args.source_path)
    except ValidationError as exc:
        first = exc.errors()[0]
        print(f"准备检查失败：配置字段 {'.'.join(map(str, first['loc']))}：{first['msg']}", file=sys.stderr)
        raise SystemExit(1) from exc
    except (OSError, ValueError, RepositoryInspectionError, RepositoryScanError,
            FileSkippedError, InvalidWorkspacePathError) as exc:
        print(f"准备检查失败：{str(exc) or type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps({"message": "准备检查通过，尚未创建实验运行", **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
