import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

import httpx

from backend.app.schemas.experiment import ExperimentPreparation, ExperimentPlanInspection
from backend.app.schemas.repository import RepositoryRead
from backend.app.schemas.task import TaskRead, TaskPlanResult


def load_prepared_experiment(path: Path) -> ExperimentPreparation:
    """读取已准备完成的实验记录，拒绝缺少任务关联的记录。"""
    preparation = ExperimentPreparation.model_validate_json(path.read_text(encoding="utf-8"))
    if preparation.status != "prepared":
        raise RuntimeError("Experiment preparation status must be prepared")
    if preparation.repository_id is None or preparation.task_id is None or not preparation.workspace_path:
        raise RuntimeError("Prepared experiment must have repository_id, task_id and workspace_path")
    if preparation.run_config.retrieval_policy not in ("vector", "hybrid"):
        raise RuntimeError("Experiment retrieval policy must be vector or hybrid")
    return preparation


def _check_task(preparation: ExperimentPreparation, task: TaskRead) -> None:
    for field, expected in (
        ("id", preparation.task_id), ("repository_id", preparation.repository_id),
        ("task_type", "plan"), ("run_config", preparation.run_config),
        ("user_request", preparation.case.user_request.strip()),
    ):
        if getattr(task, field) != expected:
            raise RuntimeError(f"Task {field} does not match experiment preparation")


def fetch_checked_task(
    client: httpx.Client, *, base_url: str, preparation: ExperimentPreparation,
) -> TaskRead:
    """从后端读取任务与仓库，确认它们属于这次实验。"""
    base_url = base_url.rstrip("/")
    response = client.get(f"{base_url}/api/v1/tasks/{preparation.task_id}")
    response.raise_for_status()
    task = TaskRead.model_validate_json(response.content)
    _check_task(preparation, task)
    response = client.get(f"{base_url}/api/v1/repositories/{preparation.repository_id}")
    response.raise_for_status()
    repository = RepositoryRead.model_validate_json(response.content)
    for field, expected in (
        ("id", preparation.repository_id), ("commit_hash", preparation.case.repository_commit),
        ("workspace_path", preparation.workspace_path), ("test_profile", preparation.case.test_profile),
    ):
        if getattr(repository, field) != expected:
            raise RuntimeError(f"Repository {field} does not match experiment preparation")
    return task


def inspect_task_plan(
    preparation: ExperimentPreparation, *, task: TaskRead,
) -> ExperimentPlanInspection:
    """检查已生成计划的修改文件，不修改计划或任务状态。"""
    if task.id != preparation.task_id or task.repository_id != preparation.repository_id:
        raise RuntimeError("Task does not belong to experiment preparation")
    scope_status = "not_checked"
    outside_scope_files = []
    if isinstance(task.result, TaskPlanResult):
        if task.result.repository_id != preparation.repository_id:
            raise RuntimeError("Plan result repository_id does not match experiment preparation")
        planned_files = {file for step in task.result.plan.steps for file in step.files}
        outside_scope_files = sorted(planned_files - set(preparation.case.editable_files))
        scope_status = "invalid" if outside_scope_files else "valid"
    elif task.status == "awaiting_review":
        raise RuntimeError("Task awaiting_review must have a valid TaskPlanResult")
    return ExperimentPlanInspection(
        experiment_id=preparation.experiment_id, task_id=task.id,
        inspected_at=datetime.now(timezone.utc), task_status=task.status,
        scope_status=scope_status, outside_scope_files=outside_scope_files,
        task=task.model_copy(deep=True),
    )


def run_or_refresh_plan(
    client: httpx.Client, *, base_url: str, preparation: ExperimentPreparation, run: bool,
) -> ExperimentPlanInspection:
    """可选地启动一次规划，随后检查返回的任务快照。"""
    task = fetch_checked_task(client, base_url=base_url, preparation=preparation)
    if run:
        if task.status != "created":
            raise RuntimeError(f"Task is {task.status}; use read-only refresh without --run")
        # 只发一次请求；超时或错误交给调用方，后续可只读刷新数据库事实。
        response = client.post(f"{base_url.rstrip('/')}/api/v1/tasks/{task.id}/run")
        response.raise_for_status()
        task = TaskRead.model_validate_json(response.content)
        _check_task(preparation, task)
        if task.status != "awaiting_review":
            raise RuntimeError(f"Planning returned unexpected status {task.status}; use read-only refresh")
    return inspect_task_plan(preparation, task=task)


def save_plan_inspection(inspection: ExperimentPlanInspection, *, output_dir: Path) -> Path:
    """每次保存新快照，不覆盖旧检查或准备记录。"""
    timestamp = inspection.inspected_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_path = output_dir / f"plan_inspection_{timestamp}_{uuid4().hex[:8]}.json"
    content = json.dumps(inspection.model_dump(mode="json"), ensure_ascii=False, indent=2)
    with output_path.open("x", encoding="utf-8") as output:
        output.write(content)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="启动一次真实规划，或只读刷新并保存实验计划检查快照")
    parser.add_argument("--preparation", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--run", action="store_true", help="启动规划，会调用模型及检索服务")
    parser.add_argument("--allow-model", action="store_true", help="明确允许本次真实模型调用")
    args = parser.parse_args()
    if args.run and not args.allow_model:
        parser.error("--run 会调用真实模型及检索服务；必须同时提供 --allow-model")
    if args.run:
        print("本次将启动真实规划，调用模型及检索服务。", flush=True)
    try:
        preparation = load_prepared_experiment(args.preparation)
        with httpx.Client(timeout=httpx.Timeout(300, connect=5)) as client:
            inspection = run_or_refresh_plan(
                client, base_url=args.base_url, preparation=preparation, run=args.run,
            )
    except httpx.TimeoutException as exc:
        print(
            "请求超时，后端可能仍在执行。\n"
            "不要立即重发 --run。\n"
            "请使用同一份 preparation.json，去掉 --run 和 --allow-model，只读刷新任务状态。",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"计划检查失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    try:
        output_path = save_plan_inspection(inspection, output_dir=args.preparation.parent)
    except Exception as exc:
        print(f"检查快照保存失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "请使用同一份 preparation.json，去掉 --run 和 --allow-model，只读刷新后重新保存。\n"
            "无需重新生成计划。",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    print(f"任务状态：{inspection.task_status}")
    print(f"范围检查：{inspection.scope_status}")
    print(f"越界文件：{json.dumps(inspection.outside_scope_files, ensure_ascii=False)}")
    print(f"检查文件：{output_path.resolve()}")
    if inspection.task_status == "awaiting_review":
        if inspection.scope_status == "valid":
            print("范围检查通过，等待人工审批")
        else:
            print("计划越界，请勿批准；原计划已保留")
    elif inspection.task_status == "running":
        print("任务仍在运行")
    elif inspection.task_status == "failed":
        print(f"任务失败：{inspection.task.error or '后端未保存错误说明'}")


if __name__ == "__main__":
    main()
