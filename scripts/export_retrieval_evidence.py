"""只读导出任务的检索证据，失败时可重新执行，不启动任务或模型。"""
import argparse
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4

import httpx
from pydantic import TypeAdapter

from backend.app.schemas.task import TaskRead
from backend.app.schemas.task_event import TaskEventRead
from backend.app.services.retrieval_report_service import build_retrieval_report, render_retrieval_report
from scripts.plan_experiment import load_prepared_experiment


def fetch_task_events(client: httpx.Client, *, base_url: str, task_id: UUID,
                      page_size: int = 100, max_events: int = 10000) -> list[TaskEventRead]:
    """游标递增直到空页；拒绝重复、错序、跨任务响应，不静默截断报告。"""
    if not 1 <= page_size <= 100 or max_events < 1:
        raise ValueError("Invalid event pagination limits")
    events = []
    cursor = 0
    while True:
        response = client.get(f"{base_url.rstrip('/')}/api/v1/tasks/{task_id}/events",
                              params={"after_sequence": cursor, "limit": page_size})
        response.raise_for_status()
        page = TypeAdapter(list[TaskEventRead]).validate_json(response.content)
        if not page:
            return events
        for event in page:
            if event.task_id != task_id or event.sequence <= cursor:
                raise ValueError("Event pagination returned another task or a non-increasing sequence")
            cursor = event.sequence
            events.append(event)
        if len(events) > max_events:
            raise ValueError("Event limit exceeded; no complete report exported")


def export_evidence(report: dict, *, output_dir: Path) -> tuple[Path, Path]:
    # 每次独立目录，即使导出中途失败也不覆盖以前的报告。
    directory = output_dir / f"retrieval_{report['task_id']}_{uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=False)
    json_path = directory / "evidence.json"
    markdown_path = directory / "evidence.md"
    with json_path.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    with markdown_path.open("x", encoding="utf-8") as output:
        output.write(render_retrieval_report(report))
    return json_path, markdown_path


def main() -> None:
    parser = argparse.ArgumentParser(description="只读导出检索与工具上下文证据，不调用模型")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--task-id", type=UUID)
    source.add_argument("--preparation", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        preparation = load_prepared_experiment(args.preparation) if args.preparation else None
        task_id = preparation.task_id if preparation else args.task_id
        with httpx.Client(timeout=30) as client:
            response = client.get(f"{args.base_url.rstrip('/')}/api/v1/tasks/{task_id}")
            response.raise_for_status()
            task = TaskRead.model_validate_json(response.content)
            if task.id != task_id:
                raise ValueError("Task response does not match requested task")
            if preparation is not None:
                for field, expected in (
                    ("repository_id", preparation.repository_id), ("run_config", preparation.run_config),
                    ("user_request", preparation.case.user_request.strip()), ("task_type", "plan"),
                ):
                    if getattr(task, field) != expected:
                        raise ValueError(f"Task {field} differs from experiment preparation")
            events = fetch_task_events(client, base_url=args.base_url, task_id=task_id)
        report = build_retrieval_report(task_id, events)
        report["task_snapshot_before_event_fetch"] = {
            "id": str(task.id), "repository_id": str(task.repository_id), "status": task.status,
            "run_config": task.run_config.model_dump(mode="json") if task.run_config else None,
        }
        report["experiment"] = ({"experiment_id": str(preparation.experiment_id),
            "case_id": preparation.case.case_id, "case_version": preparation.case.case_version,
            "repository_commit": preparation.case.repository_commit} if preparation else None)
        output_dir = args.output_dir or (args.preparation.resolve().parent / "evidence"
                                        if preparation else Path("reports/retrieval-evidence"))
        paths = export_evidence(report, output_dir=output_dir)
    except Exception as exc:
        print(f"证据导出失败：{type(exc).__name__}: {exc}\n仅重试本导出命令，不重新运行任务。", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"证据状态：{report['trace_status']}；读取 {report['event_count']} 个事件")
    print(f"JSON：{paths[0].resolve()}")
    print(f"Markdown：{paths[1].resolve()}")


if __name__ == "__main__":
    main()
