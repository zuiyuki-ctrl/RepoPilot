import argparse
from pathlib import Path
import sys
from typing import Literal

import httpx

from backend.app.schemas.experiment import ExperimentPreparation, ExperimentPlanInspection
from backend.app.schemas.task import TaskPlanReviewRequest, TaskRead
from scripts.plan_experiment import (
    load_prepared_experiment, fetch_checked_task, inspect_task_plan, save_plan_inspection,
)


def review_experiment_plan(
    client: httpx.Client, *, base_url: str, preparation: ExperimentPreparation,
    decision: Literal["approved", "rejected"], comment: str | None = None,
) -> ExperimentPlanInspection:
    """提交用户明确指定的审核决定，不启动执行。"""
    review = TaskPlanReviewRequest(decision=decision, comment=comment)
    task = fetch_checked_task(client, base_url=base_url, preparation=preparation)
    if task.status != "awaiting_review" or task.review_decision is not None:
        raise RuntimeError("Task must be awaiting_review with no existing review decision")
    inspection = inspect_task_plan(preparation, task=task)
    if review.decision == "approved" and inspection.scope_status != "valid":
        raise RuntimeError(
            f"Cannot approve plan with scope_status={inspection.scope_status}; "
            f"outside_scope_files={inspection.outside_scope_files}"
        )
    response = client.post(
        f"{base_url.rstrip('/')}/api/v1/tasks/{task.id}/review",
        json=review.model_dump(mode="json"),
    )
    response.raise_for_status()
    reviewed_task = TaskRead.model_validate_json(response.content)
    for field in ("id", "repository_id", "run_config", "user_request", "task_type", "result"):
        if getattr(reviewed_task, field) != getattr(task, field):
            raise RuntimeError(f"Reviewed task {field} differs from task before review")
    if reviewed_task.status != review.decision or reviewed_task.review_decision != review.decision:
        raise RuntimeError("Reviewed task status or review_decision does not match requested decision")
    if reviewed_task.reviewed_at is None:
        raise RuntimeError("Reviewed task has no reviewed_at timestamp")
    return inspect_task_plan(preparation, task=reviewed_task)


def _print_refresh_guidance() -> None:
    print(
        "请使用同一份 preparation.json，运行 python -m scripts.plan_experiment "
        "--preparation <准备记录路径>，不添加 --run 或 --allow-model，只读刷新当前任务状态。",
        file=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="提交明确的实验计划审核决定，不启动执行")
    parser.add_argument("--preparation", required=True, type=Path)
    parser.add_argument("--decision", required=True, choices=("approved", "rejected"))
    parser.add_argument("--comment")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        preparation = load_prepared_experiment(args.preparation)
        with httpx.Client(timeout=httpx.Timeout(300, connect=5)) as client:
            inspection = review_experiment_plan(
                client, base_url=args.base_url, preparation=preparation,
                decision=args.decision, comment=args.comment,
            )
    except httpx.TimeoutException as exc:
        print("审批请求超时，后端可能已经保存决定。不要直接重发审批请求。", file=sys.stderr)
        _print_refresh_guidance()
        raise SystemExit(1) from exc
    except httpx.HTTPStatusError as exc:
        print(f"审批请求失败：{exc}", file=sys.stderr)
        if exc.response.status_code == 409:
            print("审核状态冲突（409），不重试；请先查询当前状态。", file=sys.stderr)
            _print_refresh_guidance()
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"审核失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    try:
        output_path = save_plan_inspection(inspection, output_dir=args.preparation.parent)
    except Exception as exc:
        print(
            f"审批已成功，失败发生在本地快照保存：{type(exc).__name__}: {exc}\n"
            "请只读刷新后重新保存快照，不要重新审批。",
            file=sys.stderr,
        )
        _print_refresh_guidance()
        raise SystemExit(1) from exc
    print(f"任务 ID：{inspection.task_id}")
    print(f"审核决定：{inspection.task.review_decision}")
    print(f"任务状态：{inspection.task_status}")
    print(f"快照路径：{output_path.resolve()}")
    if inspection.task_status == "approved":
        print("已批准，尚未开始执行")


if __name__ == "__main__":
    main()
