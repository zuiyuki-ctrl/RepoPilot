import json

import httpx
import pytest

from backend.app.schemas.task_report import TaskExecutionReport
from scripts import export_task_report as exporter


@pytest.fixture
def report_data():
    task_id = "00000000-0000-0000-0000-000000000001"
    repository_id = "00000000-0000-0000-0000-000000000002"
    run_id = "00000000-0000-0000-0000-000000000003"
    timestamp = "2026-10-01T10:00:00Z"

    return {
        "task": {
            "id": task_id,
            "repository_id": repository_id,
            "user_request": "修复列表筛选",
            "task_type": "plan",
            "status": "completed",
            "created_at": timestamp,
            "started_at": timestamp,
            "completed_at": timestamp,
            "review_decision": "approved",
            "review_comment": None,
            "reviewed_at": timestamp,
            "retry_count": 1,
            "max_retries": 1,
            "error": None,
            "result": {
                "repository_id": repository_id,
                "plan": {
                    "summary": "先筛选再分页",
                    "steps": [{
                        "id": 1,
                        "description": "调整列表处理顺序",
                        "files": ["app/tasks.py"],
                        "source_ids": ["S1"],
                        "verification": "检查筛选后的分页结果",
                    }],
                },
            },
        },
        "completion_event_sequence": 12,
        "test_run": {
            "id": run_id,
            "task_id": task_id,
            "status": "finished",
            "image": "test-image",
            "timeout_seconds": 120,
            "started_at": timestamp,
            "completed_at": timestamp,
            "exit_code": 0,
            "timed_out": False,
            "stdout": "示例测试输出：1 passed",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "error": None,
            "snapshot_hash": "a" * 64,
        },
        "final_diff": {
            "task_id": task_id,
            "repository_id": repository_id,
            "diff": "-old_logic\n+saved_logic\n",
            "changed_files": ["app/tasks.py"],
            "untracked_files": ["tests/test_tasks.py"],
            "truncated": False,
        },
        "failure": None,
        "diff_scope": "workspace_against_head",
    }


def test_fetch_and_export_preserves_report(report_data, tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=report_data)

    expected = TaskExecutionReport.model_validate(report_data)
    with httpx.Client(
        transport=httpx.MockTransport(handler),
    ) as client:
        report = exporter.fetch_report(
            client,
            base_url="http://testserver",
            task_id=expected.task.id,
        )

    json_path, markdown_path = exporter.export_report(
        report,
        output_dir=tmp_path,
    )

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert saved == report.model_dump(mode="json")
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == (
        f"/api/v1/tasks/{expected.task.id}/report"
    )

    assert "修复列表筛选" in markdown
    assert "先筛选再分页" in markdown
    assert "检查筛选后的分页结果" in markdown
    assert f"- 测试运行 ID：{report.test_run.id}" in markdown
    assert "-old_logic" in markdown
    assert "+saved_logic" in markdown
    assert "### 标准输出" in markdown
    assert "### 错误输出" in markdown
    assert "### 未跟踪文件（仅记录路径）" in markdown


@pytest.mark.parametrize(
    "case",
    ["ordinary_failure", "reflection_stop", "budget_exhausted", "legacy_success"],
)
def test_terminal_report_variants(report_data, case):
    if case == "legacy_success":
        report_data["final_diff"] = None
    else:
        reason = {
            "ordinary_failure": "任务执行失败",
            "reflection_stop": "无法确认可靠修复",
            "budget_exhausted": "Task retry budget is exhausted",
        }[case]

        report_data["task"]["status"] = "failed"
        report_data["task"]["error"] = reason
        report_data["completion_event_sequence"] = None
        report_data["final_diff"] = None
        report_data["failure"] = {
            "reason": reason,
            "event_sequence": 12,
            "event_type": "TASK_FAILED",
            "reflection": None,
        }

        if case == "ordinary_failure":
            report_data["task"]["result"] = None
            report_data["test_run"] = None
        else:
            report_data["test_run"]["exit_code"] = 1
            report_data["test_run"]["stdout"] = "示例测试输出：1 failed"

        if case == "reflection_stop":
            report_data["failure"]["event_type"] = "REFLECTION_FINISHED"
            report_data["failure"]["reflection"] = {
                "diagnosis": "缺少足够证据",
                "should_retry": False,
                "actions": [],
            }

    report = TaskExecutionReport.model_validate(report_data)
    markdown = exporter.render_markdown(report)

    if case == "ordinary_failure":
        assert "任务执行失败" in markdown
        assert "未保存计划" in markdown
        assert "无关联的历史测试记录" in markdown
    elif case == "reflection_stop":
        assert "无法确认可靠修复" in markdown
        assert "缺少足够证据" in markdown
        assert "- 是否建议重试：False" in markdown
    elif case == "budget_exhausted":
        assert "Task retry budget is exhausted" in markdown
        assert "缺少足够证据" not in markdown
    else:
        assert "结果：已完成" in markdown
        assert "无已保存差异" in markdown

    assert "saved_logic" not in markdown


@pytest.mark.parametrize("status_code", [404, 409, 500, 503])
def test_http_failure_stops_export(
    monkeypatch,
    tmp_path,
    status_code,
):
    request = httpx.Request(
        "GET",
        "http://testserver/api/v1/tasks/example/report",
    )
    response = httpx.Response(status_code, request=request)
    error = httpx.HTTPStatusError(
        "Report unavailable",
        request=request,
        response=response,
    )

    def fail_fetch(*args, **kwargs):
        raise error

    def unexpected_export(*args, **kwargs):
        pytest.fail("HTTP 请求失败后不应继续导出")

    monkeypatch.setattr(exporter, "fetch_report", fail_fetch)
    monkeypatch.setattr(exporter, "export_report", unexpected_export)
    monkeypatch.setattr(
        "sys.argv",
        [
            "export_task_report",
            "--task-id",
            "00000000-0000-0000-0000-000000000001",
            "--output-dir",
            str(tmp_path),
        ],
    )

    with pytest.raises(httpx.HTTPStatusError):
        exporter.main()

    assert list(tmp_path.iterdir()) == []
