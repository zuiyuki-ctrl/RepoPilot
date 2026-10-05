import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx

from backend.app.schemas.task import TaskPlanResult
from backend.app.schemas.task_report import TaskExecutionReport


def fetch_report(
    client: httpx.Client,
    *,
    base_url: str,
    task_id: UUID,
) -> TaskExecutionReport:
    url = f"{base_url.rstrip('/')}/api/v1/tasks/{task_id}/report"
    response = client.get(url)
    response.raise_for_status()
    return TaskExecutionReport.model_validate(response.json())


def append_literal(lines: list[str], content: str) -> None:
    # 给自由文本留出空行，再逐行缩进，使它作为 Markdown 原样文本显示。
    lines.append("")
    for line in content.splitlines() or ["（空）"]:
        lines.append(f"    {line}")


def append_field(lines: list[str], label: str, value: object) -> None:
    display = "未记录" if value is None else str(value)
    lines.append(f"- {label}：{display}")


def render_markdown(report: TaskExecutionReport) -> str:
    task = report.task
    lines = [
        "# RepoPilot 任务报告",
        "",
        f"- 任务 ID：{task.id}",
        f"- 仓库 ID：{task.repository_id}",
        f"- 状态：{task.status}",
        f"- 创建时间：{task.created_at.isoformat()}",
        "",
        "## 任务目标",
        "",
    ]

    # 1. 加入 task.user_request。
    #    自由文本建议作为独立段落或安全的代码块，不要直接拼进 Markdown 表格。
    append_literal(lines, task.user_request)

    lines.extend(["", "## 计划", ""])
    if isinstance(task.result, TaskPlanResult):
        plan = task.result.plan

        # 2. 展示 plan.summary。
        append_literal(lines, plan.summary)

        # 3. 遍历 plan.steps，展示 id、description、files、verification。
        for step in plan.steps:
            lines.append(f"### 步骤 {step.id}")
            append_literal(lines, step.description)

            for file in step.files:
                append_literal(lines, file)

            append_literal(lines, step.verification)
    else:
        # 4. 历史失败任务可能没有保存计划；明确写“未保存计划”。
        lines.append("未保存计划")

    lines.extend(["", "## 终态与测试", ""])
    failure = report.failure
    if failure is None:
        # 5. 展示 completion_event_sequence。
        #    完成依据来自 report.test_run；不要另找“最新测试”。
        lines.append("结果：已完成")
        append_field(lines, "终止事件序号", report.completion_event_sequence)
    else:
        # 6. 展示 failure.reason、event_type、event_sequence。
        #    failure.reflection 非空时，展示真实保存的诊断与决定。
        #    不要为普通 TASK_FAILED 编造 Reflection 内容。
        lines.append("结果：失败")
        append_literal(lines, failure.reason)
        append_field(lines, "失败事件类型", failure.event_type)
        append_field(lines, "失败事件序号", failure.event_sequence)

        if failure.reflection is not None:
            append_literal(lines, failure.reflection.diagnosis)
            append_field(lines, "是否建议重试", failure.reflection.should_retry)

    if report.test_run is not None:
        run = report.test_run
        # 7. 展示 run.id、status、exit_code、timed_out、
        #    image、snapshot_hash、stdout、stderr。
        #    同时展示 stdout_truncated / stderr_truncated，
        #    让读者知道输出是否被截断。
        append_field(lines, "测试运行 ID", run.id)
        append_field(lines, "运行状态", run.status)
        append_field(lines, "退出码", run.exit_code)
        append_field(lines, "是否超时", run.timed_out)
        append_field(lines, "运行镜像", run.image)
        append_field(lines, "快照哈希", run.snapshot_hash)
        append_literal(lines, run.stdout)
        append_literal(lines, run.stderr)
        append_field(lines, "输出已截断", run.stdout_truncated)
        append_field(lines, "错误输出已截断", run.stderr_truncated)
    else:
        # 8. 明确写“无关联的历史测试记录”。
        lines.append("无关联的历史测试记录")


    lines.extend(["", "## 完成时差异", ""])
    if report.final_diff is not None:
        diff = report.final_diff
        # 9. 展示 report.diff_scope、changed_files、
        #    untracked_files、truncated、diff.diff。
        #    注意：untracked_files 当前只有路径，不能声称包含文件正文。
        append_field(lines, "差异范围", report.diff_scope)
        append_field(lines, "差异已截断", diff.truncated)

        for file in diff.changed_files:
            append_literal(lines, file)

        for file in diff.untracked_files:
            append_literal(lines, file)

        append_literal(lines, diff.diff)
    else:
        # 10. 失败报告或旧成功报告可能没有保存 final_diff。
        #     明确写“无已保存差异”，不要读取当前工作区补齐。
        lines.append("无已保存差异")

    return "\n".join(lines) + "\n"


def export_report(
    report: TaskExecutionReport,
    *,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    # 使用时间戳，重复导出不会覆盖上一份文件。
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    stem = f"task_{report.task.id}_{timestamp}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"

    payload = report.model_dump(mode="json")
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_markdown(report),
        encoding="utf-8",
    )
    return json_path, markdown_path


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 RepoPilot 历史任务报告")
    parser.add_argument("--task-id", required=True, type=UUID)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/tasks"),
    )
    args = parser.parse_args()

    with httpx.Client(timeout=15.0) as client:
        report = fetch_report(
            client,
            base_url=args.base_url,
            task_id=args.task_id,
        )

    json_path, markdown_path = export_report(
        report,
        output_dir=args.output_dir,
    )
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")


if __name__ == "__main__":
    main()
