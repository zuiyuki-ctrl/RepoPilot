import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from backend.app.services.test_report_parser import parse_test_report, read_test_report
from backend.app.services.evaluation_metrics_service import (
    test_metrics as measure_tests, resource_metrics, estimate_cost, build_run_metrics, aggregate_metrics,
)
from backend.app.services import docker_test_service as docker
from backend.app.services.sandbox_snapshot_service import SandboxSnapshot


XML = b'<testsuites><testsuite tests="4" failures="1" errors="1" skipped="1"><testcase name="a"/><testcase name="b"><failure/></testcase><testcase name="c"><error/></testcase><testcase name="d"><skipped/></testcase></testsuite></testsuites>'


def observation(call_id="one", **changes):
    obs = dict(request_attempted=True, requested_model="sample", usage_status="complete",
               duration_ms=30, usage=dict(input_tokens=10, output_tokens=5, total_tokens=15))
    obs.update(changes)
    return dict(call_id=call_id, kind="chat", phase="model", completeness="recorded", observation=obs)


class StructuredTestReportTests(unittest.TestCase):
    def test_counts_include_failures_collection_errors_and_skips(self):
        report = parse_test_report(XML)
        self.assertEqual(report["counts"], dict(passed=1, failed=1, errors=1, skipped=1))
        run = SimpleNamespace(id=UUID(int=1), test_report=report, timed_out=False, status="finished")
        self.assertEqual(measure_tests(run)["pass_rate"], .25)
        report["counts"]["passed"] = 100
        self.assertIsNone(measure_tests(run)["counts"])

    def test_missing_invalid_entities_size_and_mismatched_counts(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(read_test_report(Path(tmp) / "missing")["status"], "missing")
        for data in (b'broken', b'<!DOCTYPE x [<!ENTITY y "hi">]><testsuite/>', b'x' * 1_000_001,
                     XML.replace(b'tests="4"', b'tests="5"')):
            self.assertIsNone(parse_test_report(data)["counts"])

    def test_empty_suite_has_no_pass_rate(self):
        report = parse_test_report(b'<testsuite tests="0" failures="0" errors="0" skipped="0"/>')
        run = SimpleNamespace(id=UUID(int=1), test_report=report, timed_out=False, status="finished")
        self.assertIsNone(measure_tests(run)["pass_rate"])

    def test_docker_reads_separate_report_before_cleanup(self):
        with TemporaryDirectory() as tmp:
            snapshot = SandboxSnapshot(root=Path(tmp), files=[], total_bytes=0, snapshot_hash="a" * 64)
            def run(command, **kwargs):
                mount = next(arg for arg in command if arg.endswith("target=/test-results"))
                directory = Path(mount.split("source=", 1)[1].rsplit(",target=", 1)[0])
                (directory / "junit.xml").write_bytes(XML)
                self.assertIn("--junitxml=/test-results/junit.xml", command)
                self.assertIn("--read-only", command)
                self.output_dir = directory
                return docker.SandboxTestResult(1, "failed", "", False, False, False)
            with patch.object(docker, "_run_docker_process", side_effect=run):
                result = docker.run_pytest_in_docker(snapshot)
            self.assertEqual(result.test_report["counts"]["errors"], 1)
            self.assertFalse(self.output_dir.exists())

    def test_real_pytest_junit_setup_and_teardown_protocol(self):
        import pytest
        import io
        from contextlib import redirect_stdout, redirect_stderr
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "test_sample.py").write_text(
                "import pytest\n"
                "@pytest.fixture\ndef setup_error():\n    raise RuntimeError('setup')\n"
                "@pytest.fixture\ndef teardown_error():\n    yield\n    raise RuntimeError('teardown')\n"
                "def test_ok():\n    assert True\n"
                "def test_setup(setup_error):\n    pass\n"
                "def test_teardown(teardown_error):\n    pass\n", encoding="utf-8")
            path = root / "junit.xml"
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = pytest.main([str(root / "test_sample.py"), "--rootdir=" + str(root),
                                    "--confcutdir=" + str(root), "--import-mode=importlib", "-q", "-p", "no:cacheprovider",
                                    "--junitxml=" + str(path), "-o", "junit_family=xunit2"])
            self.assertNotEqual(code, 0)
            report = read_test_report(path)
            self.assertEqual(report["status"], "recorded")
            self.assertEqual(report["counts"], dict(passed=1, failed=0, errors=2, skipped=0), report["xml"])


class ResourceMetricsTests(unittest.TestCase):
    def test_failed_business_output_still_counts_usage(self):
        row = observation(operation_status="failed")
        self.assertEqual(resource_metrics([row], complete_scope=True)["total_tokens"], 15)

    def test_missing_duplicate_and_partial_scope_never_claim_total(self):
        for rows, scope in (([observation(), observation()], True),
                            ([observation(), observation("two", usage_status="missing")], True),
                            ([observation()], False)):
            self.assertIsNone(resource_metrics(rows, complete_scope=scope)["total_tokens"])
        self.assertEqual(resource_metrics([observation(), observation()], complete_scope=True)["known_total_tokens"], 0)

    def test_not_attempted_does_not_count_as_request(self):
        metric = resource_metrics([observation(request_attempted=False)], complete_scope=True)
        self.assertEqual(metric["attempted_calls"], 0)
        self.assertEqual(metric["known_not_attempted"], 1)

    def test_pricing_missing_is_unknown(self):
        self.assertIsNone(estimate_cost([observation()], None, complete_scope=True)["total"])

    def test_price_snapshot_and_cache_coverage(self):
        prices = dict(version="example-only", currency="TEST", effective_date="2026-10-12",
                      source="synthetic test", models={"sample": dict(input_per_million="2", output_per_million="4")})
        result = estimate_cost([observation()], prices, complete_scope=True)
        self.assertEqual(result["total"], "0.00004")
        prices["models"]["sample"]["cached_input_per_million"] = "1"
        self.assertIsNone(estimate_cost([observation()], prices, complete_scope=True)["total"])
        prices["models"]["sample"]["input_per_million"] = "NaN"
        with self.assertRaises(ValueError):
            estimate_cost([observation()], prices, complete_scope=True)

    def test_legacy_full_events_are_not_full_instrumentation(self):
        now = datetime.now(timezone.utc)
        task = SimpleNamespace(status="completed", started_at=now, completed_at=now)
        events = [SimpleNamespace(sequence=1, event_type="TASK_STARTED", payload={})]
        metric = build_run_metrics(task, None, events, terminal_sequence=1)
        self.assertTrue(metric["started"])
        self.assertIsNone(metric["resources"]["total_tokens"])
        self.assertEqual(metric["acceptance"]["outcome"], "unknown")

    def test_started_failures_stay_in_denominator_unknown_stays_visible(self):
        now = datetime.now(timezone.utc)
        event = SimpleNamespace(sequence=1, event_type="TASK_STARTED", payload={})
        failed = build_run_metrics(SimpleNamespace(status="failed", started_at=now, completed_at=now), None, [event], terminal_sequence=1)
        unknown = build_run_metrics(SimpleNamespace(status="completed", started_at=now, completed_at=now), None, [event], terminal_sequence=1)
        aggregate = aggregate_metrics([failed, unknown, None])
        self.assertEqual(aggregate["started_runs"], 2)
        self.assertEqual(aggregate["start_unknown_runs"], 1)
        self.assertEqual(aggregate["provisional_success_rate"], 0)
        self.assertIsNone(aggregate["final_success_rate"])
