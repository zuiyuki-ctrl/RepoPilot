import argparse
from contextlib import contextmanager
import sys
from uuid import UUID

import httpx
from pydantic import ValidationError

from backend.app.schemas.task import TaskRead
from backend.app.schemas.task_report import TaskExecutionReport
from backend.app.schemas.testing import TaskTestRead
from scripts.export_task_report import fetch_report


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


# 已批准且处于 executing 的计划任务才可使用；后端负责最终状态与快照检查。
def main() -> None:
    parser = argparse.ArgumentParser(description="运行任务测试，通过后请求完成任务并读取历史报告")
    parser.add_argument("--task-id", required=True, type=UUID)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        with httpx.Client(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
            test_result, report = test_and_complete_task(client, base_url=args.base_url, task_id=args.task_id)
    except TaskWorkflowError as exc:
        print(f"失败阶段：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if report is None:
        print(f"test_run_id={test_result.test_run_id} exit_code={test_result.exit_code} timed_out={test_result.timed_out}")
        print("测试未通过，任务未完成。")
        raise SystemExit(1)

    print(f"task_id={args.task_id} test_run_id={test_result.test_run_id} status=completed")
    print(f"changed_files={report.final_diff.changed_files}" if report.final_diff is not None
          else "changed_files：未记录")


if __name__ == "__main__":
    main()
