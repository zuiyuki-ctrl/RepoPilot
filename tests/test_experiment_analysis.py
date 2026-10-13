"""Synthetic-only fixtures: never exported into the real experiment manifest."""
from copy import deepcopy
from itertools import product
import unittest
from uuid import UUID

from backend.app.services.experiment_analysis_service import (
    PAIR_CATEGORIES, analyze_failure, analyze_pair, summarize_pairs,
)
from backend.app.services.test_report_parser import parse_test_report


def synthetic_row(outcome="not_passed"):
    return {"experiment_id": "synthetic-only", "task_id": str(UUID(int=1)),
            "completed_at": "2026-10-13T00:00:00+00:00", "status": "failed",
            "preparation_status": "prepared", "run_config": {},
            "acceptance": {"outcome": outcome},
            "failure": {"reason": "timeout retrieval budget test failure", "event_sequence": 10,
                        "event_type": "TASK_FAILED"}, "test": None, "final_diff": None}


def synthetic_test(outcome="failed"):
    child = {"failed": "<failure message='assertion'/>", "errors": "<error message='setup'/>",
             "skipped": "<skipped/>", "passed": ""}[outcome]
    report = parse_test_report((f'<testsuite tests="1" failures="{int(outcome == "failed")}" '
        f'errors="{int(outcome == "errors")}" skipped="{int(outcome == "skipped")}">'
        f'<testcase classname="tests.test_example" name="test_target">{child}</testcase></testsuite>').encode())
    return {"id": str(UUID(int=2)), "status": "finished", "exit_code": 1, "error": None,
            "timed_out": False, "test_report": report, "stdout": "synthetic output"}


class PairAnalysisTests(unittest.TestCase):
    def test_all_outcome_combinations_and_conditions(self):
        expected = {("passed", "passed"): "stayed_success", ("not_passed", "passed"): "improved",
                    ("passed", "not_passed"): "regressed", ("not_passed", "not_passed"): "both_not_success"}
        for a, b, conditions in product(("passed", "not_passed", "unknown"),
                                        ("passed", "not_passed", "unknown"),
                                        ("different", "insufficient_evidence", "recorded_conditions_match")):
            with self.subTest(a=a, b=b, conditions=conditions):
                result = analyze_pair(synthetic_row(a), synthetic_row(b), {"status": conditions})
                category = ("non_comparable" if conditions == "different" else
                            expected.get((a, b), "undecided") if conditions == "recorded_conditions_match"
                            else "undecided")
                self.assertEqual(result["category"], category)
                self.assertEqual(result["acceptance_outcomes"], dict(baseline=a, candidate=b))

    def test_missing_pair_and_observed_model_drift_block_conclusion(self):
        conditions = {"status": "recorded_conditions_match"}
        self.assertEqual(analyze_pair(None, synthetic_row(), conditions)["reason"], "paired_run_missing")
        self.assertEqual(analyze_pair(synthetic_row(), synthetic_row("passed"), conditions,
            observed_differences=["observed_models"])["category"], "non_comparable")

    def test_legacy_process_pass_is_not_success(self):
        row = synthetic_row("unknown")
        row["test"] = {"process_passed": True}
        result = analyze_pair(row, row, {"status": "insufficient_evidence"})
        self.assertTrue(result["both_test_processes_passed"])
        self.assertEqual(result["category"], "undecided")

    def test_counts_include_undecided_and_noncomparable(self):
        result = summarize_pairs([{"analysis": {"category": category}} for category in PAIR_CATEGORIES])
        self.assertEqual(result["primary_pairs"], 6)
        self.assertEqual(result["classified_pairs"], 4)
        self.assertEqual(sum(result["counts"].values()), 6)
        self.assertEqual(result["classification_coverage"], 4 / 6)
        self.assertIsNone(summarize_pairs([])["classification_coverage"])


class FailureAnalysisTests(unittest.TestCase):
    def test_error_words_do_not_infer_root_cause(self):
        result = analyze_failure(synthetic_row())
        self.assertEqual(result["primary_category"], "UNKNOWN")
        self.assertEqual(result["termination_stage"], "unknown")
        self.assertEqual(result["root_cause_status"], "unknown")
        self.assertIn("terminal_saved_diff", result["missing_evidence"])

    def test_assertion_error_skip_and_timeout_are_facts_not_root_causes(self):
        for outcome, kind in (("failed", "test_failure_reported"), ("errors", "test_error_reported"),
                              ("skipped", "test_skipped")):
            with self.subTest(outcome=outcome):
                row = synthetic_row()
                row["test"] = synthetic_test(outcome)
                result = analyze_failure(row)
                self.assertIn(kind, [fact["kind"] for fact in result["facts"]])
                self.assertEqual(result["primary_category"], "UNKNOWN")
                report = next(e for e in result["evidence"] if e["id"] == "test_report")
                self.assertEqual(report["value"]["nonpassing_tests"][0]["name"], "test_target")
        row["test"]["timed_out"] = True
        result = analyze_failure(row)
        self.assertIn("test_timeout", [f["kind"] for f in result["facts"]])
        self.assertEqual(result["primary_category"], "UNKNOWN")

    def test_tampered_xml_and_stdout_not_used_as_counts(self):
        row = synthetic_row()
        row["test"] = synthetic_test()
        row["test"]["test_report"]["counts"]["failed"] = 0
        row["test"]["stdout"] = "12 failed"
        result = analyze_failure(row)
        self.assertNotIn("test_report", [e["id"] for e in result["evidence"]])
        self.assertIn("usable_structured_test_report", result["missing_evidence"])

    def test_budget_code_only_classifies_termination(self):
        row = synthetic_row()
        row["failure"]["reason_code"] = "retry_budget_exhausted"
        result = analyze_failure(row)
        self.assertEqual(result["primary_category"], "BUDGET_EXCEEDED")
        self.assertEqual(result["termination_stage"], "recovery")
        self.assertEqual(result["root_cause_status"], "unknown")

    def test_reflection_diagnosis_stays_unreviewed_model_hypothesis(self):
        row = synthetic_row()
        row["failure"].update(event_type="REFLECTION_FINISHED",
            reflection={"diagnosis": "retrieval failed", "should_retry": False})
        result = analyze_failure(row)
        self.assertEqual(result["hypotheses"][0]["source"], "model_reflection")
        self.assertEqual(result["review_status"], "unreviewed")
        self.assertEqual(result["primary_category"], "UNKNOWN")

    def test_preparation_error_is_not_a_started_task_failure(self):
        row = dict(status="preparation_error", preparation_status="error", preparation_stage="embedding",
                   preparation_error_type="TimeoutError", task_id=None)
        result = analyze_failure(row)
        self.assertEqual(result["termination_stage"], "preparation")
        self.assertEqual(result["primary_category"], "UNKNOWN")
        self.assertIn("terminal_event", result["missing_evidence"])

    def test_request_failure_keeps_stage_and_event_not_root_cause(self):
        row = synthetic_row()
        request = dict(call_id="one", kind="chat", phase="planning", finished_sequences=[5],
            completeness="recorded", observation=dict(call_id="one", operation_status="failed",
                failure_stage="business_validation", error_type="ValueError"))
        row["metrics"] = {"request_observations": [request]}
        result = analyze_failure(row)
        self.assertIn("planning", result["observed_stages"])
        self.assertEqual(result["termination_stage"], "unknown")
        self.assertEqual(result["primary_category"], "UNKNOWN")
        event = next(e for e in result["evidence"] if e["id"].startswith("request:"))
        self.assertEqual(event["value"]["finished_sequences"], [5])
        request["completeness"] = "ambiguous"
        self.assertNotIn("planning", analyze_failure(row)["observed_stages"])

    def test_review_binding_and_read_only_inputs(self):
        row = synthetic_row()
        row["test"] = synthetic_test()
        row["retrieval"] = {"queries": [{"event_sequence": 2, "hits": [], "diagnostics": {"candidate_count": 9}}]}
        before = deepcopy(row)
        result = analyze_failure(row)
        review = dict(task_id=row["task_id"], analysis_sha256=result["analysis_sha256"], reviewer="tester",
            recorded_at="2026-10-13T01:00:00+00:00", primary_category="EDIT_FAILURE",
            hypothesis="Synthetic manual assessment", evidence_ids=["final_test", "test_report", "retrieval:2"],
            rationale="Synthetic reviewer examined named testcase evidence")
        approved = analyze_failure(row, review=review)
        self.assertEqual(approved["review_status"], "reviewed")
        self.assertEqual(approved["source"], "manual")
        self.assertEqual(approved["root_cause_status"], "human_assessed")
        self.assertEqual(row, before)
        self.assertEqual(analyze_failure(row)["analysis_sha256"], result["analysis_sha256"])
        for key, value in (("task_id", str(UUID(int=99))), ("analysis_sha256", "a" * 64),
                           ("recorded_at", "2020-01-01T00:00:00+00:00"), ("recorded_at", "2026-10-13T01:00:00"),
                           ("evidence_ids", ["not_present"]), ("evidence_ids", ["final_test", "final_test"]),
                           ("primary_category", "MADE_UP"), ("reviewer", "  ")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                analyze_failure(row, review={**review, key: value})
        row["test"]["stdout"] = "edited evidence"
        with self.assertRaises(ValueError):
            analyze_failure(row, review=review)

    def test_completed_unknown_is_not_silently_failure_or_success(self):
        row = synthetic_row("unknown")
        row.update(status="completed", failure=None, completion_event_sequence=10)
        result = analyze_failure(row)
        self.assertEqual(result["status"], "no_failure_observed")
        self.assertEqual(result["review_status"], "not_requested")

    def test_diff_is_only_historical_and_hash_bound(self):
        row = synthetic_row()
        row["final_diff"] = {"diff": "saved diff", "changed_files": ["example.py"],
                             "untracked_files": [], "truncated": True}
        before = deepcopy(row)
        result = analyze_failure(row)
        diff = next(e for e in result["evidence"] if e["id"] == "final_diff")
        self.assertTrue(diff["value"]["truncated"])
        self.assertEqual(diff["source"], "report.final_diff")
        self.assertEqual(row, before)


if __name__ == "__main__":
    unittest.main()
