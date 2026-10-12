import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Literal
from uuid import uuid4

from backend.app.schemas.experiment import ExperimentCase, ExperimentPreparation
from backend.app.schemas.repository import RepositoryCreate
from backend.app.schemas.run_config import AgentRunConfig
from backend.app.schemas.experiment_definition import ExperimentDefinition
from backend.app.services.experiment_contract_service import validate_definition, contract_digest, baseline_satisfies_rule
from backend.app.services.experiment_baseline_service import capture_baseline_test
from backend.app.schemas.task import TaskCreate
from backend.app.services.repository_service import create_repository, update_repository_test_profile
from backend.app.services.repository_indexing_service import index_repository_chunks
from backend.app.services.repository_embedding_service import embed_repository_chunks
from backend.app.services.task_service import create_task
from backend.app.services.experiment_conditions_service import capture_experiment_conditions
from scripts.prepare_experiment import inspect_experiment_source, load_experiment_case


def save_preparation(record: ExperimentPreparation, *, output_path: Path) -> None:
    """保存当前准备阶段，便于定位部分成功后的失败。"""
    content = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output_path.parent,
            prefix=f".{output_path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def prepare_experiment_run(
    case: ExperimentCase, *, source_path: Path,
    retrieval_policy: Literal["vector", "hybrid"], output_dir: Path,
    definition: ExperimentDefinition | None = None, allow_baseline_tests: bool = False,
) -> ExperimentPreparation:
    """创建一次独立实验所需的仓库、索引和 created 状态任务。"""
    if definition is not None:
        validate_definition(case, definition)
        if case.task_type == "bug_fix" and not allow_baseline_tests:
            raise ValueError("Controlled bug-fix preparation requires --allow-baseline-tests")
    summary = inspect_experiment_source(case, source_path=source_path)
    if retrieval_policy not in ("vector", "hybrid"):
        raise ValueError("Experiment retrieval policy must be vector or hybrid")
    record = ExperimentPreparation(
        experiment_id=uuid4(), created_at=datetime.now(timezone.utc),
        case=case.model_copy(deep=True),
        run_config=AgentRunConfig(retrieval_policy=retrieval_policy, max_tool_calls=4),
        status="preparing", stage="initialize",
        embedding_observations=[],
        definition=definition.model_copy(deep=True) if definition else None,
        protected_test_file_hashes=summary["protected_test_file_hashes"],
        source_protected_test_file_hashes=summary["protected_test_file_hashes"],
    )
    run_dir = output_dir / str(record.experiment_id)
    run_dir.mkdir(parents=True, exist_ok=False)
    output_path = run_dir / "preparation.json"

    def stage(name: str) -> None:
        record.stage = name
        save_preparation(record, output_path=output_path)

    def embedding_sink(event: dict) -> None:
        record.embedding_observations.append({**event, "scope": "preparation_index",
            "experiment_id": str(record.experiment_id), "repository_id": str(record.repository_id)})
        save_preparation(record, output_path=output_path)

    try:
        save_preparation(record, output_path=output_path)
        stage("register_repository")
        repository = create_repository(RepositoryCreate(
            name=f"{case.case_id}-{retrieval_policy}-{record.experiment_id}",
            source_path=summary["source_path"],
        ))
        if repository is None:
            raise ValueError("Repository registration returned None")
        record.repository_id = repository.id
        record.workspace_path = repository.workspace_path
        save_preparation(record, output_path=output_path)
        if repository.commit_hash != case.repository_commit:
            raise ValueError("Registered repository commit mismatch")
        if not repository.workspace_path:
            raise ValueError("Registered repository has no workspace path")
        workspace_path = Path(repository.workspace_path).resolve()
        if workspace_path == Path(summary["source_path"]).resolve():
            raise ValueError("Workspace must be independent of source repository")

        stage("inspect_workspace")
        workspace_summary = inspect_experiment_source(case, source_path=workspace_path)
        expected_files = set(case.protected_test_files)
        if (
            set(workspace_summary["protected_test_file_hashes"]) != expected_files
            or set(summary["protected_test_lf_hashes"]) != expected_files
            or workspace_summary["protected_test_lf_hashes"] != summary["protected_test_lf_hashes"]
        ):
            raise ValueError("Workspace protected test content mismatch (beyond CRLF/LF conversion)")
        # 初次检出内容确认一致后，冻结实际工作副本原始字节作为执行期基线。
        # 不修改文件，不在之后的执行检查中归一化换行或更新基线。
        record.protected_test_file_hashes = dict(workspace_summary["protected_test_file_hashes"])
        save_preparation(record, output_path=output_path)

        stage("update_test_profile")
        if update_repository_test_profile(repository.id, test_profile=case.test_profile) is None:
            raise ValueError("Test profile update returned None")
        stage("index_repository_chunks")
        index = index_repository_chunks(repository.id)
        if index is None:
            raise ValueError("Repository indexing returned None")
        if index.skipped_files or index.chunk_count == 0:
            raise ValueError("Experiment requires a complete, nonempty chunk index")
        stage("embedding")
        if embed_repository_chunks(repository.id, observation_sink=embedding_sink) is None:
            raise ValueError("Repository embedding returned None")

        stage("capture_conditions")
        record.conditions = capture_experiment_conditions(repository.id, test_profile=case.test_profile)
        record.run_config = AgentRunConfig(retrieval_policy=retrieval_policy,
            max_tool_calls=definition.max_tool_calls if definition else 4,
            runtime_fingerprint=record.conditions["runtime_fingerprint"],
            index_fingerprint=record.conditions["index_fingerprint"],
            test_image_id=record.conditions["test_image"]["id"])
        save_preparation(record, output_path=output_path)

        if definition is not None:
            if record.run_config.test_image_id is None:
                raise ValueError("Controlled experiments require a recorded test image ID")
            if case.task_type == "bug_fix":
                stage("baseline_tests")
                record.baseline_test = capture_baseline_test(record)
                save_preparation(record, output_path=output_path)
                if not baseline_satisfies_rule(record):
                    raise ValueError("Baseline tests do not demonstrate the declared bug; inspect saved baseline evidence")
            record.run_config = record.run_config.model_copy(update={
                "experiment_contract_sha256": contract_digest(record)})
            save_preparation(record, output_path=output_path)

        stage("create_task")
        task = create_task(TaskCreate(
            repository_id=repository.id, user_request=case.user_request,
            task_type="plan", run_config=record.run_config,
        ))
        if task is None:
            raise ValueError("Task creation returned None")
        record.task_id = task.id
        save_preparation(record, output_path=output_path)
        if (task.repository_id != repository.id or task.status != "created"
                or task.run_config != record.run_config):
            raise ValueError("Created task does not match experiment configuration")
        record.status = "prepared"
        save_preparation(record, output_path=output_path)
        return record
    except Exception as exc:
        record.status = "error"
        record.error_type = type(exc).__name__
        print(
            f"实验准备失败：experiment_id={record.experiment_id} "
            f"repository_id={record.repository_id} stage={record.stage} "
            f"error_type={record.error_type}", file=sys.stderr,
        )
        try:
            save_preparation(record, output_path=output_path)
        except Exception as save_error:
            print(f"错误记录保存失败：{type(save_error).__name__}: {save_error}", file=sys.stderr)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="准备独立实验；包含真实 Embedding 向量化请求，不运行任务")
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--source-path", required=True, type=Path)
    parser.add_argument("--retrieval-policy", required=True, choices=("vector", "hybrid"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/experiments"))
    parser.add_argument("--allow-embedding", action="store_true", help="明确允许本次真实 Embedding 向量化请求")
    parser.add_argument("--definition", type=Path, help="运行前声明的版本化实验定义")
    parser.add_argument("--allow-baseline-tests", action="store_true", help="允许在修改前启动 Docker 基线测试")
    args = parser.parse_args()
    if not args.allow_embedding:
        parser.error("本命令包含真实 Embedding 向量化请求；请使用 --allow-embedding 明确允许")
    print("本次准备将调用 Embedding 服务，产生真实向量化请求。", flush=True)
    try:
        record = prepare_experiment_run(
            load_experiment_case(args.case), source_path=args.source_path,
            retrieval_policy=args.retrieval_policy, output_dir=args.output_dir,
            definition=ExperimentDefinition.model_validate_json(args.definition.read_bytes()) if args.definition else None,
            allow_baseline_tests=args.allow_baseline_tests,
        )
    except Exception as exc:
        print(f"准备失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"实验 ID：{record.experiment_id}")
    print(f"仓库 ID：{record.repository_id}")
    print(f"任务 ID：{record.task_id}")
    print(f"记录文件：{(args.output_dir / str(record.experiment_id) / 'preparation.json').resolve()}")
    print("准备完成；任务尚未运行，尚未审批。")


if __name__ == "__main__":
    main()
