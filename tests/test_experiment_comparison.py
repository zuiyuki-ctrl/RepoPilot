"""历史 artifact 的离线集成与篡改回归；网络在整个测试类中禁止。"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.compare_experiments import load_comparison, export_comparison
from backend.app.services.experiment_comparison_service import summarize_run, build_comparison


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evals/experiments/comparison-v1.json"


class ExperimentComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        cls.network.start()
        cls.addClassCleanup(cls.network.stop)
        entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["runs"]
        entry = next(item for item in entries if "statistics-hybrid" in item["preparation"])
        cls.fixture = {name: json.loads((MANIFEST.parent / entry[name]).resolve().read_bytes())
                       for name in ("preparation", "report", "evidence")}

    def test_real_six_runs_and_additional_attempts(self):
        result = load_comparison(MANIFEST)
        self.assertEqual(len(result["pairs"]), 3)
        self.assertTrue(all(pair["pair_complete"] for pair in result["pairs"]))
        self.assertEqual(result["primary_status_counts"]["vector"]["completed"], 3)
        self.assertEqual(result["primary_status_counts"]["hybrid"]["completed"], 3)
        self.assertEqual({r["status"] for r in result["additional_attempts"]},
                         {"preparation_incomplete", "preparation_error"})
        old = next(pair for pair in result["pairs"] if pair["case_id"] == "task-list")["runs"]["vector"]
        self.assertEqual(old["retrieval"]["trace_status"], "not_recorded")
        self.assertIsNone(old["token_usage"])
        self.assertIsNone(old["test"]["structured_test_counts"])
        self.assertEqual(result["paired_analysis_summary"]["primary_pairs"], 3)
        self.assertEqual(result["paired_analysis_summary"]["counts"]["undecided"], 3)
        self.assertEqual(result["paired_analysis_summary"]["classified_pairs"], 0)
        self.assertTrue(all(p["analysis"]["both_test_processes_passed"] for p in result["pairs"]))
        self.assertTrue(all(p["analysis"]["category"] != "improved" for p in result["pairs"]))

    def test_no_input_mutation_and_raw_events_override_edited_summary(self):
        data = deepcopy(self.fixture)
        data["evidence"]["tool_calls"] = []
        before = deepcopy(data)
        row = summarize_run(**data)
        self.assertEqual(len(row["retrieval"]["queries"]), 2)
        self.assertEqual(data, before)

    def test_reject_report_identity_config_mismatches(self):
        for field, value in (("id", "00000000-0000-0000-0000-000000000001"),
                             ("repository_id", "00000000-0000-0000-0000-000000000001"),
                             ("user_request", "changed"), ("task_type", "question")):
            with self.subTest(field=field):
                data = deepcopy(self.fixture)
                data["report"]["task"][field] = value
                with self.assertRaises(ValueError):
                    summarize_run(**data)
        data = deepcopy(self.fixture)
        data["report"]["task"]["run_config"]["retrieval_policy"] = "vector"
        with self.assertRaises(ValueError):
            summarize_run(**data)

    def test_reject_wrong_test_and_unpassed_completed(self):
        for field, value in (("task_id", "00000000-0000-0000-0000-000000000001"),
                             ("exit_code", 1), ("timed_out", True), ("snapshot_hash", None)):
            with self.subTest(field=field):
                data = deepcopy(self.fixture)
                data["report"]["test_run"][field] = value
                with self.assertRaises(ValueError):
                    summarize_run(**data)

    def test_reject_changed_test_in_diff(self):
        data = deepcopy(self.fixture)
        data["report"]["final_diff"]["changed_files"].append("tests/test_statistics.py")
        with self.assertRaises(ValueError):
            summarize_run(**data)

    def test_missing_evidence_is_unknown(self):
        data = deepcopy(self.fixture)
        data["evidence"] = None
        self.assertIsNone(summarize_run(**data)["retrieval"])

    def test_reject_wrong_evidence_and_actual_strategy(self):
        data = deepcopy(self.fixture)
        data["evidence"]["experiment"]["case_version"] = "v999"
        with self.assertRaises(ValueError):
            summarize_run(**data)
        data = deepcopy(self.fixture)
        event = next(e for e in data["evidence"]["events"] if e["event_type"] == "RETRIEVAL_COMPLETED")
        event["payload"]["retrieval_strategy"] = "vector"
        with self.assertRaises(ValueError):
            summarize_run(**data)

    def test_reject_invalid_event_snapshot(self):
        data = deepcopy(self.fixture)
        data["evidence"]["event_count"] = 0
        with self.assertRaises(ValueError):
            summarize_run(**data)

    def test_duplicate_primary_and_reused_task_rejected(self):
        row = summarize_run(**self.fixture)
        row.update(role="primary", artifacts={})
        with self.assertRaises(ValueError):
            build_comparison([row, deepcopy(row)])
        other = deepcopy(row)
        other["experiment_id"] = "different"
        with self.assertRaises(ValueError):
            build_comparison([row, other])
        other["task_id"] = "different"
        with self.assertRaises(ValueError):
            build_comparison([row, other])

    def test_missing_pair_and_mismatched_conditions_visible(self):
        row = summarize_run(**self.fixture)
        row.update(role="primary", artifacts={})
        self.assertFalse(build_comparison([row])["pairs"][0]["pair_complete"])
        other = deepcopy(row)
        other.update(experiment_id="other", task_id="other", strategy="vector")
        other["case"]["repository_commit"] = "f" * 40
        result = build_comparison([row, other])
        self.assertIn("case", result["pairs"][0]["recorded_condition_differences"])

    def test_failure_is_not_dropped(self):
        data = deepcopy(self.fixture)
        data["report"]["task"]["status"] = "failed"
        data["report"]["task"]["error"] = "Failure"
        data["report"]["completion_event_sequence"] = None
        data["report"]["failure"] = {"reason": "Failure", "event_sequence": 31, "event_type": "TASK_FAILED"}
        data["report"]["test_run"]["exit_code"] = 1
        row = summarize_run(**data)
        row.update(role="primary", artifacts={})
        self.assertEqual(build_comparison([row])["primary_status_counts"]["hybrid"]["failed"], 1)

    def test_exports_unique_and_preserves_original_stdout(self):
        result = load_comparison(MANIFEST)
        with tempfile.TemporaryDirectory() as directory:
            paths = export_comparison(result, Path(directory))
            again = export_comparison(result, Path(directory))
            self.assertNotEqual(paths, again)
            text = paths[1].read_text(encoding="utf-8")
            self.assertIn("12 passed in 0.11s", text)
            self.assertIn("preparation_incomplete", text)
            self.assertIn("not_recorded", text)
            self.assertIn("配对变化（独立验收口径）", text)
            self.assertIn("失败证据分析", text)
            self.assertIn("undecided", text)

    def test_missing_file_rejected_without_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps({"runs": [{"preparation": "missing.json"}]}))
            with self.assertRaises(OSError):
                load_comparison(path)

    def test_synthetic_failure_review_manifest_roundtrip(self):
        # 复制历史结构构造模拟失败；只写临时目录，不改真实六条记录。
        data = deepcopy(self.fixture)
        data["report"]["task"].update(status="failed", error="Synthetic failure")
        data["report"].update(completion_event_sequence=None, final_diff=None,
            failure=dict(reason="Synthetic failure", event_sequence=31, event_type="TASK_FAILED"))
        data["report"]["test_run"]["exit_code"] = 1
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = {name: name + ".json" for name in data}
            for name, value in data.items():
                (root / entry[name]).write_text(json.dumps(value), encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"runs": [entry]}), encoding="utf-8")
            initial = load_comparison(manifest)
            row = initial["pairs"][0]["runs"]["hybrid"]
            review = dict(task_id=row["task_id"], analysis_sha256=row["failure_analysis"]["analysis_sha256"],
                reviewer="synthetic-reviewer", recorded_at=row["completed_at"], primary_category="UNKNOWN",
                hypothesis="Insufficient synthetic evidence", evidence_ids=["terminal_event", "final_test"],
                rationale="Test process failed; no causal conclusion")
            (root / "review.json").write_text(json.dumps(review), encoding="utf-8")
            entry["failure_review"] = "review.json"
            manifest.write_text(json.dumps({"runs": [entry]}), encoding="utf-8")
            reviewed = load_comparison(manifest)
            actual = reviewed["pairs"][0]["runs"]["hybrid"]
            self.assertEqual(actual["failure_analysis"]["review_status"], "reviewed")
            self.assertEqual(actual["failure_analysis"]["root_cause_status"], "unknown")
            self.assertEqual(actual["acceptance"], row["acceptance"])
            self.assertEqual(reviewed["paired_analysis_summary"], initial["paired_analysis_summary"])
            self.assertIsNotNone(actual["artifacts"]["failure_review"]["sha256"])
            paths = export_comparison(reviewed, root)
            self.assertIn("synthetic-reviewer", paths[1].read_text(encoding="utf-8"))
            data["report"]["test_run"]["stdout"] += " changed"
            (root / "report.json").write_text(json.dumps(data["report"]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Failure review differs"):
                load_comparison(manifest)

    def test_review_without_terminal_report_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "terminal task report"):
            summarize_run(self.fixture["preparation"], None, None, failure_review={})

    def test_synthetic_batch_decision_review_is_not_plan_approval(self):
        # 仅读取历史文件；复核是测试夹具，只保存在临时目录。
        manifest_data = json.loads(MANIFEST.read_bytes())
        for entry in manifest_data["runs"]:
            for name in ("preparation", "report", "evidence"):
                if entry.get(name):
                    entry[name] = str((MANIFEST.parent / entry[name]).resolve())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
            initial = load_comparison(manifest)
            self.assertEqual(initial["decision"]["verdict"], "insufficient_evidence")
            review = dict(decision_sha256=initial["decision"]["decision_sha256"], reviewer="synthetic",
                recorded_at="2026-10-13T00:00:00Z", action="continue_experiment", rationale="Synthetic test only")
            (root / "review.json").write_text(json.dumps(review), encoding="utf-8")
            manifest_data["decision_review"] = "review.json"
            manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
            checked = load_comparison(manifest)
            self.assertEqual(checked["decision"]["review"]["action"], "continue_experiment")
            self.assertEqual(checked["decision"]["verdict"], initial["decision"]["verdict"])
            self.assertIsNotNone(checked["decision_review_artifact"]["sha256"])
            review["decision_sha256"] = "0" * 64
            (root / "review.json").write_text(json.dumps(review), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_comparison(manifest)


if __name__ == "__main__":
    unittest.main()
