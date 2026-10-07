import argparse
from contextlib import contextmanager
from pathlib import Path
import sys
from uuid import UUID

import httpx
from pydantic import ValidationError

from backend.app.schemas.task import TaskRead
from backend.app.schemas.task_report import TaskExecutionReport
from backend.app.schemas.testing import TaskTestRead
from scripts.export_task_report import fetch_report, export_report


# 保留失败阶段和原始异常，供命令行区分 HTTP 拒绝、超时和响应异常。
class TaskWorkflowError(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"{stage}：{message}")
        self.stage = stage


@contextmanager
def _stage(name: str):
    try:
        yield
    except httpx.TimeoutException as exc:
        raise TaskWorkflowError(name, "HTTP 超时；后端可能仍在执行，请查询任务与测试记录，勿立即重发请求。") from exc
    except httpx.HTTPStatusError as exc:
        raise TaskWorkflowError(name, f"HTTP {exc.response.status_code}，请求未成功；请检查任务与测试记录。") from exc
    except httpx.HTTPError as exc:
        raise TaskWorkflowError(name, "网络请求失败，请查询任务与测试记录后确认结果。") from exc
    except ValidationError as exc:
        raise TaskWorkflowError(name, "响应不符合预期 Schema") from exc
    except OSError as exc:
        raise TaskWorkflowError(
            name,
            "本地文件操作失败；这不表示后端任务失败。"
            "请检查输出目录，可能已有部分文件写入。",
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise TaskWorkflowError(name, str(exc)) from exc


# 仅串联用户明确要求的测试、完成和历史报告请求；失败即停止，不重试 POST。
def test_and_complete_task(
    client: httpx.Client,
    *,
    base_url: str,
    task_id: UUID,
) -> tuple[TaskTestRead, TaskExecutionReport | None]:
    """运行一次测试；通过后尝试完成任务，并返回历史报告。"""
    task_url = f"{base_url.rstrip('/')}/api/v1/tasks/{task_id}"
    with _stage("运行测试"):
        response = client.post(f"{task_url}/tests")
        response.raise_for_status()
        test_result = TaskTestRead.model_validate(response.json())
        if test_result.task_id != task_id:
            raise RuntimeError("测试响应的任务 ID 不一致")
        if test_result.passed != (not test_result.timed_out and test_result.exit_code == 0):
            raise RuntimeError("测试响应的通过状态与退出码、超时标记不一致")

    if not test_result.passed:
        return test_result, None

    with _stage("完成任务"):
        response = client.post(f"{task_url}/complete", json={"test_run_id": str(test_result.test_run_id)})
        response.raise_for_status()
        task = TaskRead.model_validate(response.json())
        if task.id != task_id or task.status != "completed":
            raise RuntimeError("完成响应的任务 ID 或状态不符合预期")

    with _stage("读取报告"):
        report = fetch_report(client, base_url=base_url, task_id=task_id)
        if report.task.id != task_id:
            raise RuntimeError("报告的任务 ID 不一致")
        if report.test_run is None or report.test_run.id != test_result.test_run_id:
            raise RuntimeError("报告未关联本次测试运行")

    return test_result, report


def save_completed_report(
    report: TaskExecutionReport,
    *,
    task_id: UUID,
    expected_test_run_id: UUID | None,
    output_dir: Path,
) -> tuple[Path, Path]:
    if report.task.id != task_id:
        raise RuntimeError("报告的任务 ID 不一致")

    if (
        report.task.status != "completed"
        or report.failure is not None
        or report.completion_event_sequence is None
    ):
        raise RuntimeError("报告不是已完成计划任务的终态报告")

    run = report.test_run
    if run is None or run.task_id != task_id:
        raise RuntimeError("报告未关联该任务的测试运行")

    if (
        run.status != "finished"
        or run.exit_code != 0
        or run.timed_out
    ):
        raise RuntimeError("报告关联的测试运行未成功完成")

    if expected_test_run_id is not None and run.id != expected_test_run_id:
        raise RuntimeError("报告未关联本次测试运行")

    return export_report(report, output_dir=output_dir)


# 已批准且处于 executing 的计划任务才可使用；后端负责最终状态与快照检查。
def main() -> None:
    parser = argparse.ArgumentParser(description="运行任务测试，通过后请求完成任务并读取历史报告")
    parser.add_argument("--task-id", required=True, type=UUID)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/tasks"),
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="只读取并导出已完成任务的历史报告，不运行测试或请求完成",
    )
    args = parser.parse_args()

    try:
        with httpx.Client(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
            expected_test_run_id = None

            if args.report_only:
                with _stage("读取报告"):
                    report = fetch_report(
                        client,
                        base_url=args.base_url,
                        task_id=args.task_id,
                    )
            else:
                test_result, report = test_and_complete_task(
                    client,
                    base_url=args.base_url,
                    task_id=args.task_id,
                )

                if report is None:
                    print(
                        f"test_run_id={test_result.test_run_id} "
                        f"exit_code={test_result.exit_code} "
                        f"timed_out={test_result.timed_out}"
                    )
                    print("测试未通过，任务未完成。")
                    raise SystemExit(1)

                expected_test_run_id = test_result.test_run_id

        with _stage("导出报告"):
            json_path, markdown_path = save_completed_report(
                report,
                task_id=args.task_id,
                expected_test_run_id=expected_test_run_id,
                output_dir=args.output_dir,
            )
    except TaskWorkflowError as exc:
        print(f"失败阶段：{exc}", file=sys.stderr)
        if exc.stage == "导出报告":
            print(
                "报告未成功导出；不要因此重新运行测试，\n"
                "排查后可使用 --report-only 重新读取并导出。",
                file=sys.stderr,
            )
        raise SystemExit(2) from exc

    print(f"task_id={args.task_id} status=completed")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")


if __name__ == "__main__":
    main()
