import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from unittest.mock import patch
from uuid import UUID

import httpx

from scripts import test_and_complete_task as script


class TestAndCompleteTaskTests(unittest.TestCase):
    def setUp(self):
        self.task_id = UUID(int=1)
        self.run_id = UUID(int=2)
        self.test_result = dict(task_id=str(self.task_id), test_run_id=str(self.run_id),
            passed=True, exit_code=0, timed_out=False, stdout="1 passed", stderr="",
            stdout_truncated=False, stderr_truncated=False)
        self.task = dict(id=str(self.task_id), repository_id=str(UUID(int=3)),
            user_request="修复", task_type="plan", status="completed", result=None,
            created_at="2026-10-07T00:00:00Z", started_at=None,
            completed_at="2026-10-07T00:00:00Z", error=None, review_decision="approved",
            review_comment=None, reviewed_at=None)
        self.run = dict(id=str(self.run_id), task_id=str(self.task_id), status="finished",
            image="test-image", timeout_seconds=60, started_at="2026-10-07T00:00:00Z",
            completed_at="2026-10-07T00:00:01Z", exit_code=0, timed_out=False,
            stdout="1 passed", stderr="", stdout_truncated=False, stderr_truncated=False,
            error=None, snapshot_hash=None)
        self.report = dict(task=deepcopy(self.task), test_run=self.run,
            completion_event_sequence=10, final_diff=None)
        self.responses = [self.test_result, self.task, self.report]
        self.requests = []

    def client(self):
        def handle(request):
            self.requests.append(request)
            item = self.responses[len(self.requests) - 1]
            if isinstance(item, Exception):
                raise item
            if isinstance(item, int):
                return httpx.Response(item, json={"detail": "rejected"})
            return httpx.Response(200, json=item)
        return httpx.Client(transport=httpx.MockTransport(handle))

    def run_flow(self):
        with self.client() as client:
            return script.test_and_complete_task(client, base_url="http://example.test/", task_id=self.task_id)

    def test_success_uses_returned_run_id_and_only_three_requests(self):
        result, report = self.run_flow()
        self.assertEqual(result.test_run_id, self.run_id)
        self.assertEqual(report.test_run.id, self.run_id)
        self.assertEqual([(r.method, r.url.path) for r in self.requests], [
            ("POST", f"/api/v1/tasks/{self.task_id}/tests"),
            ("POST", f"/api/v1/tasks/{self.task_id}/complete"),
            ("GET", f"/api/v1/tasks/{self.task_id}/report")])
        self.assertEqual(json.loads(self.requests[1].content), {"test_run_id": str(self.run_id)})

    def test_failed_or_timed_out_test_never_completes(self):
        for exit_code, timed_out in ((1, False), (0, True), (None, True)):
            with self.subTest(exit_code=exit_code, timed_out=timed_out):
                self.requests.clear()
                self.test_result.update(passed=False, exit_code=exit_code, timed_out=timed_out)
                result, report = self.run_flow()
                self.assertFalse(result.passed)
                self.assertIsNone(report)
                self.assertEqual(len(self.requests), 1)

    def test_bad_test_response_stops_before_completion(self):
        for change in ({"task_id": str(UUID(int=9))}, {"passed": False},
                       {"exit_code": 1}, {"timed_out": True}, {"test_run_id": "bad"}):
            with self.subTest(change=change):
                self.requests.clear()
                self.responses[0] = {**self.test_result, **change}
                with self.assertRaises(script.TaskWorkflowError) as raised:
                    self.run_flow()
                self.assertEqual(raised.exception.stage, "运行测试")
                self.assertEqual(len(self.requests), 1)

    def test_http_rejections_stop_without_retry(self):
        for index, status, stage in ((0, 503, "运行测试"), (1, 409, "完成任务"), (2, 500, "读取报告")):
            with self.subTest(stage=stage):
                self.requests.clear()
                self.responses = [self.test_result, self.task, self.report]
                self.responses[index] = status
                with self.assertRaises(script.TaskWorkflowError) as raised:
                    self.run_flow()
                self.assertEqual(raised.exception.stage, stage)
                self.assertEqual(raised.exception.__cause__.response.status_code, status)
                self.assertEqual(len(self.requests), index + 1)

    def test_bad_completion_response_stops_before_report(self):
        for change in ({"id": str(UUID(int=9))}, {"status": "executing"}):
            with self.subTest(change=change):
                self.requests.clear()
                self.responses[1] = {**self.task, **change}
                with self.assertRaises(script.TaskWorkflowError) as raised:
                    self.run_flow()
                self.assertEqual(raised.exception.stage, "完成任务")
                self.assertEqual(len(self.requests), 2)

    def test_report_must_reference_this_task_and_run(self):
        for change in ({"task": {**self.task, "id": str(UUID(int=9))}},
                       {"test_run": None}, {"test_run": {**self.run, "id": str(UUID(int=9))}}):
            with self.subTest(change=change):
                self.requests.clear()
                self.responses[2] = {**self.report, **change}
                with self.assertRaises(script.TaskWorkflowError) as raised:
                    self.run_flow()
                self.assertEqual(raised.exception.stage, "读取报告")

    def test_timeouts_never_retry_and_explain_uncertainty(self):
        for index in (0, 1):
            with self.subTest(index=index):
                self.requests.clear()
                self.responses = [self.test_result, self.task, self.report]
                self.responses[index] = httpx.ReadTimeout("timed out")
                with self.assertRaisesRegex(script.TaskWorkflowError, "后端可能仍在执行"):
                    self.run_flow()
                self.assertEqual(len(self.requests), index + 1)

    def test_cli_exit_codes_and_timeouts(self):
        for case, expected_code in (("success", 0), ("failed", 1), ("timeout", 2)):
            with self.subTest(case=case):
                self.requests.clear()
                self.responses = [dict(self.test_result), self.task, self.report]
                if case == "failed":
                    self.responses[0].update(passed=False, exit_code=1)
                if case == "timeout":
                    self.responses[0] = httpx.ReadTimeout("timed out")
                client = self.client()
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(script.httpx, "Client", return_value=client) as factory, \
                     patch("sys.argv", ["test_and_complete_task", "--task-id", str(self.task_id)]), \
                     redirect_stdout(stdout), redirect_stderr(stderr):
                    if expected_code:
                        with self.assertRaises(SystemExit) as raised:
                            script.main()
                        self.assertEqual(raised.exception.code, expected_code)
                    else:
                        script.main()
                timeout = factory.call_args.kwargs["timeout"]
                self.assertEqual(timeout.read, 300)
                self.assertEqual(timeout.connect, 5)
                if case == "success":
                    self.assertIn("status=completed", stdout.getvalue())
                    self.assertIn("未记录", stdout.getvalue())
                elif case == "failed":
                    self.assertIn("任务未完成", stdout.getvalue())
                else:
                    self.assertIn("运行测试", stderr.getvalue())
                    self.assertIn("勿立即重发", stderr.getvalue())
