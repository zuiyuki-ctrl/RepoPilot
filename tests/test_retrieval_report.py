from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import json
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx

from backend.app.schemas.task_event import TaskEventRead
from backend.app.services.retrieval_report_service import build_retrieval_report, render_retrieval_report
from scripts.export_retrieval_evidence import fetch_task_events, export_evidence
from scripts import export_retrieval_evidence as cli


TASK_ID = UUID(int=1)


def event(sequence, kind, payload, node="tools", task_id=TASK_ID):
    return TaskEventRead(id=uuid4(), task_id=task_id, sequence=sequence,
        event_type=kind, node_name=node, message="test", payload=payload,
        created_at=datetime.now(timezone.utc))


def trace():
    base = dict(call_id="internal-tool", tool_call_id="model-tool", tool_name="search_code", trace_version=1)
    ref = dict(tool_message_index=0, tool_call_id="model-tool", content_sha256="a" * 64, content_chars=50)
    return [
        event(1, "RETRIEVAL_COMPLETED", {**base, "query": "中文 symbol", "retrieval_strategy": "vector",
            "hits": [{"rank": 1, "chunk_id": "chunk", "content_sha256": "b" * 64}]}),
        event(2, "TOOL_CONTEXT_PREPARED", {**base, **ref, "disposition": "accepted",
            "sources": [{"chunk_id": "chunk", "source_id": "S1"}]}),
        event(3, "MODEL_CALL_STARTED", {"call_id": "model-1", "trace_version": 1, "tool_context": [ref]}, "model"),
        event(4, "MODEL_CALL_COMPLETED", {"call_id": "model-1"}, "model"),
    ]


class RetrievalReportTests(unittest.TestCase):
    def test_trace_links_without_mutating_events(self):
        events = trace()
        before = deepcopy(events)
        report = build_retrieval_report(TASK_ID, events)
        row = report["tool_calls"][0]
        self.assertEqual(report["trace_status"], "recorded")
        self.assertEqual(row["retrieval"]["sequence"], 1)
        self.assertEqual(row["context"]["sequence"], 2)
        self.assertEqual(row["model_calls"][0]["started_sequence"], 3)
        self.assertEqual(row["model_calls"][0]["outcome"], "completed")
        self.assertEqual(events, before)

    def test_old_events_are_unrecorded_not_empty_retrieval_success(self):
        events = [event(1, "TOOL_CALL_COMPLETED", dict(call_id="old", tool_call_id="call",
                  tool_name="search_code", retrieval_strategy="vector", hit_count=3))]
        report = build_retrieval_report(TASK_ID, events)
        self.assertEqual(report["trace_status"], "not_recorded")
        self.assertIsNone(report["tool_calls"][0]["retrieval"])
        self.assertIn("未记录", render_retrieval_report(report))
        self.assertEqual(report["events"][0]["payload"]["hit_count"], 3)

    def test_discarded_result_is_not_rendered_as_accepted_source(self):
        events = trace()
        events[1].payload.update(disposition="discarded", sources=[])
        report = build_retrieval_report(TASK_ID, events)
        row = report["tool_calls"][0]
        self.assertEqual(len(row["retrieval"]["payload"]["hits"]), 1)
        self.assertEqual(row["context"]["payload"]["sources"], [])
        self.assertEqual(row["model_calls"][0]["outcome"], "completed")
        self.assertIn('"disposition": "discarded"', render_retrieval_report(report))

    def test_no_context_or_no_later_model_does_not_claim_submission(self):
        for events in (trace()[:1], trace()[:2]):
            report = build_retrieval_report(TASK_ID, events)
            self.assertEqual(report["tool_calls"][0]["model_calls"], [])
            self.assertIn("不能推断已提交", render_retrieval_report(report))

    def test_failed_and_pending_model_outcomes_remain_distinct(self):
        events = trace()
        events[3].event_type = "MODEL_CALL_FAILED"
        report = build_retrieval_report(TASK_ID, events)
        self.assertEqual(report["tool_calls"][0]["model_calls"][0]["outcome"], "failed")
        pending = build_retrieval_report(TASK_ID, events[:3])
        self.assertEqual(pending["model_calls"][0]["outcome"], "unrecorded")

    def test_same_tool_id_different_hash_or_position_is_not_matched(self):
        for field, value in (("content_sha256", "f" * 64), ("tool_message_index", 1), ("content_chars", 51)):
            events = trace()
            # fixture 的 ref 被两事件共用，先深拷贝模型 payload 再修改。
            events[2].payload = deepcopy(events[2].payload)
            events[2].payload["tool_context"][0][field] = value
            with self.subTest(field=field):
                report = build_retrieval_report(TASK_ID, events)
                self.assertEqual(report["tool_calls"][0]["model_calls"], [])
                self.assertEqual(len(report["model_calls"][0]["unmatched_tool_context"]), 1)
                self.assertEqual(report["trace_status"], "partial")

    def test_duplicate_matching_context_is_ambiguous(self):
        events = trace()
        duplicate = event(3, "TOOL_CONTEXT_PREPARED", {**events[1].payload, "call_id": "another-tool"})
        events[2].sequence = 4
        events[3].sequence = 5
        report = build_retrieval_report(TASK_ID, [*events[:2], duplicate, *events[2:]])
        self.assertTrue(report["warnings"])
        self.assertTrue(all(not row["model_calls"] for row in report["tool_calls"]))

    def test_unknown_trace_version_and_missing_sequence_are_explicit(self):
        events = trace()
        events[0].payload["trace_version"] = 99
        report = build_retrieval_report(TASK_ID, events)
        self.assertIsNone(report["tool_calls"][0]["retrieval"])
        self.assertTrue(report["warnings"])
        self.assertEqual(report["events"][0]["payload"]["trace_version"], 99)
        gap = build_retrieval_report(TASK_ID, events[1:])
        self.assertTrue(any("缺口" in warning for warning in gap["warnings"]))

    def test_wrong_task_order_and_conflicting_tool_identity_are_rejected(self):
        events = trace()
        for invalid in (
            [events[1], events[0]],
            [events[0].model_copy(update={"task_id": uuid4()})],
            [events[0].model_copy(update={"payload": {**events[0].payload, "sequence": 2}})],
            [events[0], events[1].model_copy(update={"payload": {**events[1].payload, "tool_call_id": "different"}})],
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                build_retrieval_report(TASK_ID, invalid)

    def test_export_keeps_previous_artifacts_and_literal_query(self):
        events = trace()
        events[0].payload["query"] = "# fake heading\n<script>data</script>"
        report = build_retrieval_report(TASK_ID, events)
        with TemporaryDirectory() as directory:
            first, markdown = export_evidence(report, output_dir=Path(directory))
            original = first.read_bytes()
            second, _ = export_evidence(report, output_dir=Path(directory))
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), original)
            self.assertEqual(json.loads(original), report)
            self.assertNotIn("\n# fake heading", markdown.read_text(encoding="utf-8"))


class EventPaginationTests(unittest.TestCase):
    def test_reads_short_pages_until_empty_with_only_get_requests(self):
        requests = []
        def handle(request):
            requests.append(request)
            cursor = int(request.url.params["after_sequence"])
            page = [e.model_dump(mode="json") for e in trace() if cursor < e.sequence <= cursor + 1]
            return httpx.Response(200, json=page)
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            events = fetch_task_events(client, base_url="http://test/", task_id=TASK_ID)
        self.assertEqual(len(events), 4)
        self.assertEqual([r.url.params["after_sequence"] for r in requests], ["0", "1", "2", "3", "4"])
        self.assertTrue(all(r.method == "GET" for r in requests))

    def test_repeated_cross_task_and_unbounded_pages_are_rejected(self):
        for mode in ("repeat", "wrong_task", "limit"):
            count = 0
            def handle(request):
                nonlocal count
                count += 1
                item = event(count if mode == "limit" else 1, "TASK_STARTED", {},
                             task_id=uuid4() if mode == "wrong_task" else TASK_ID)
                return httpx.Response(200, json=[item.model_dump(mode="json")])
            with self.subTest(mode=mode), httpx.Client(transport=httpx.MockTransport(handle)) as client:
                with self.assertRaises(ValueError):
                    fetch_task_events(client, base_url="http://test", task_id=TASK_ID, max_events=2)
                self.assertLessEqual(count, 3)

    def test_http_failure_is_not_treated_as_an_empty_history(self):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503))) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                fetch_task_events(client, base_url="http://test", task_id=TASK_ID)

    def test_cli_checks_preparation_association_before_exporting(self):
        now = datetime.now(timezone.utc).isoformat()
        repository_id = str(UUID(int=2))
        run_config = {"schema_version": 1, "retrieval_policy": "vector", "max_tool_calls": 4}
        preparation = dict(schema_version=1, experiment_id=str(uuid4()), created_at=now,
            status="prepared", stage="create_task", task_id=str(TASK_ID), repository_id=repository_id,
            workspace_path="D:/unused", protected_test_file_hashes={"tests/test_x.py": "a" * 64},
            run_config=run_config, case=dict(case_id="sample", case_version="v1", task_type="bug_fix",
                user_request=" fix ", repository_commit="a" * 40, editable_files=["x.py"],
                protected_test_files=["tests/test_x.py"], test_profile="python-basic"))
        task = dict(id=str(TASK_ID), repository_id=repository_id, user_request="fix", task_type="plan",
            status="completed", created_at=now, started_at=now, completed_at=now, result=None,
            error=None, review_decision="approved", review_comment=None, reviewed_at=now, run_config=run_config)
        for mismatch in (False, True):
            requests = []
            def handle(request):
                requests.append(request)
                if request.url.path.endswith("/events"):
                    return httpx.Response(200, json=[])
                return httpx.Response(200, json={**task, "repository_id": str(uuid4())} if mismatch else task)
            with self.subTest(mismatch=mismatch), TemporaryDirectory() as directory:
                path = Path(directory) / "preparation.json"
                path.write_text(json.dumps(preparation), encoding="utf-8")
                client = httpx.Client(transport=httpx.MockTransport(handle))
                with patch.object(cli.httpx, "Client", return_value=client), \
                        patch.object(cli.sys, "argv", ["export", "--preparation", str(path)]), \
                        redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    if mismatch:
                        with self.assertRaises(SystemExit) as raised:
                            cli.main()
                        self.assertEqual(raised.exception.code, 1)
                        self.assertEqual(len(requests), 1)
                        self.assertFalse((Path(directory) / "evidence").exists())
                    else:
                        cli.main()
                        saved = next((Path(directory) / "evidence").glob("*/evidence.json"))
                        payload = json.loads(saved.read_text(encoding="utf-8"))
                        self.assertEqual(payload["experiment"]["experiment_id"], preparation["experiment_id"])
                        self.assertEqual(payload["trace_status"], "not_recorded")
                        self.assertEqual(len(requests), 2)
                self.assertTrue(all(request.method == "GET" for request in requests))
