from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID
import unittest

from backend.app.schemas.experiment import ExperimentPreparation
from backend.app.schemas.experiment_definition import ExperimentDefinition, RequiredTest
from backend.app.services.experiment_contract_service import (
    contract_digest, require_contract, evaluate_acceptance, compare_conditions, validate_definition,
)
from backend.app.services.experiment_comparison_service import build_comparison
from backend.app.services.test_report_parser import parse_test_report


def junit(outcome="passed", name="test_example"):
    child = "" if outcome == "passed" else {"failed": "<failure/>", "errors": "<error/>", "skipped": "<skipped/>"}[outcome]
    return parse_test_report((f'<testsuite tests="1" failures="{int(outcome == "failed")}" errors="{int(outcome == "errors")}" skipped="{int(outcome == "skipped")}">'
        f'<testcase classname="tests.test_example" name="{name}">{child}</testcase></testsuite>').encode())


def definition():
    target = dict(classname="tests.test_example", name="test_example")
    return ExperimentDefinition(suite_id="synthetic", suite_version="v2", config_version="v1", repeat_index=1,
        acceptance=dict(version="v2", required_tests=[target], baseline_failure_tests=[target]))


class ExperimentContractTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.prep = ExperimentPreparation(experiment_id=UUID(int=1), created_at=self.now,
            case=dict(case_id="sample", case_version="v2", task_type="bug_fix", user_request="fix",
                repository_commit="a" * 40, editable_files=["example.py"],
                protected_test_files=["tests/test_example.py"], test_profile="python-basic"),
            run_config=dict(retrieval_policy="vector", runtime_fingerprint="b" * 64,
                index_fingerprint="c" * 64, test_image_id="sha256:" + "d" * 64),
            status="prepared", stage="create_task", repository_id=UUID(int=2), task_id=UUID(int=3),
            protected_test_file_hashes={"tests/test_example.py": "e" * 64}, definition=definition(),
            conditions=dict(runtime_fingerprint="b" * 64, index_fingerprint="c" * 64,
                test_image={"id": "sha256:" + "d" * 64}))
        self.prep.baseline_test = dict(test_report=junit("failed"), exit_code=1, timed_out=False,
            image=self.prep.run_config.test_image_id, timeout_seconds=120, snapshot_hash="f" * 64,
            repository_commit=self.prep.case.repository_commit,
            protected_test_file_hashes=self.prep.protected_test_file_hashes)
        self.seal()
        self.report = SimpleNamespace(task=SimpleNamespace(id=UUID(int=3), status="completed", completed_at=self.now),
            test_run=SimpleNamespace(id=UUID(int=4), status="finished", image=self.prep.run_config.test_image_id,
                timeout_seconds=120, exit_code=0, timed_out=False, error=None, test_report=junit()))

    def seal(self):
        self.prep.run_config = self.prep.run_config.model_copy(update={"experiment_contract_sha256": contract_digest(self.prep)})

    def test_bug_fix_requires_failed_before_and_passed_after(self):
        self.assertEqual(evaluate_acceptance(self.prep, self.report)["outcome"], "passed")
        self.prep.baseline_test["test_report"] = junit()
        self.seal()
        self.assertEqual(evaluate_acceptance(self.prep, self.report)["reason"], "baseline_failure_evidence_missing")

    def test_missing_required_test_is_unknown_even_exit_zero(self):
        self.report.test_run.test_report = junit(name="other_test")
        self.assertEqual(evaluate_acceptance(self.prep, self.report)["reason"], "required_tests_missing")

    def test_skip_and_error_not_accepted(self):
        for outcome in ("skipped", "errors", "failed"):
            self.report.test_run.test_report = junit(outcome)
            self.assertEqual(evaluate_acceptance(self.prep, self.report)["outcome"], "not_passed")

    def test_feature_needs_no_failed_baseline(self):
        self.prep.case.task_type = "feature"
        self.prep.baseline_test = None
        self.seal()
        self.assertEqual(evaluate_acceptance(self.prep, self.report)["outcome"], "passed")

    def test_mutated_contract_and_invalid_scope_are_rejected(self):
        self.prep.definition.acceptance.version = "changed"
        with self.assertRaises(ValueError):
            require_contract(self.prep)
        invalid = definition()
        invalid.acceptance.required_tests[0] = RequiredTest(classname="unprotected", name="x")
        with self.assertRaises(ValueError):
            validate_definition(self.prep.case, invalid)

    def test_manual_review_is_bound_to_final_report(self):
        self.prep.definition.acceptance.manual_criteria = ["preserves input"]
        self.seal()
        self.assertEqual(evaluate_acceptance(self.prep, self.report)["reason"], "manual_acceptance_review_required")
        review = dict(task_id=str(self.report.task.id), test_run_id=str(self.report.test_run.id),
            contract_sha256=self.prep.run_config.experiment_contract_sha256,
            test_report_sha256=self.report.test_run.test_report["sha256"], reviewer="human",
            recorded_at=self.now.isoformat(), decision="approved", checked_criteria=["preserves input"], evidence="checked input mutation test and diff")
        self.assertEqual(evaluate_acceptance(self.prep, self.report, review=review)["outcome"], "passed")
        review["test_run_id"] = str(UUID(int=99))
        with self.assertRaises(ValueError):
            evaluate_acceptance(self.prep, self.report, review=review)

    def row(self, strategy="vector", repeat=1):
        runtime = {key: "recorded" for key in ("chat_model", "embedding_model", "embedding_dimensions", "chat_parameters",
            "prompt_templates_sha256", "tool_definitions_sha256", "context_budget_chars", "implementation_sha256", "provider_internal_version")}
        return dict(experiment_id=str(UUID(int=10 + repeat * 2 + (strategy == "hybrid"))), task_id=None,
            role="primary", case=self.prep.case.model_dump(mode="json"), strategy=strategy, repeat_index=repeat,
            definition={**self.prep.definition.model_dump(mode="json"), "repeat_index": repeat},
            run_config=self.prep.run_config.model_dump(mode="json"), max_retries=1, status="completed",
            protected_test_file_hashes=self.prep.protected_test_file_hashes, metrics=None, retrieval=None,
            conditions={**self.prep.conditions, "runtime": runtime},
            test=dict(image=self.prep.run_config.test_image_id, timeout_seconds=120))

    def test_conditions_compare_inputs_not_queries_or_context(self):
        a, b = self.row(), self.row("hybrid")
        b["retrieval"] = {"queries": ["different"], "model_calls": []}
        self.assertEqual(compare_conditions(a, b)["status"], "recorded_conditions_match")
        b["conditions"]["runtime"]["chat_model"] = "other"
        result = compare_conditions(a, b)
        self.assertEqual(result["status"], "different")
        self.assertIn("runtime.chat_model", [d["field"] for d in result["differences"]])

    def test_provider_unknown_and_legacy_are_not_comparable(self):
        a, b = self.row(), self.row("hybrid")
        a["conditions"]["runtime"]["provider_internal_version"] = None
        self.assertEqual(compare_conditions(a, b)["status"], "insufficient_evidence")
        a["definition"] = b["definition"] = None
        self.assertIn("definition", compare_conditions(a, b)["missing"])

    def test_repeat_pairing_keeps_all_attempts(self):
        rows = [self.row(strategy, repeat) for repeat in (1, 2) for strategy in ("vector", "hybrid")]
        before = deepcopy(rows)
        report = build_comparison(rows)
        self.assertEqual([p["repeat_index"] for p in report["pairs"]], [1, 2])
        self.assertEqual(rows, before)
        duplicate = self.row()
        duplicate["experiment_id"] = "extra"
        with self.assertRaises(ValueError):
            build_comparison(rows + [duplicate])

    def test_synthetic_controlled_pairs_classify_but_do_not_modify_inputs(self):
        for left, right, expected in (("passed", "passed", "stayed_success"),
                ("not_passed", "passed", "improved"), ("passed", "not_passed", "regressed"),
                ("not_passed", "not_passed", "both_not_success")):
            with self.subTest(expected=expected):
                a, b = self.row(), self.row("hybrid")
                a["acceptance"], b["acceptance"] = {"outcome": left}, {"outcome": right}
                before = deepcopy([a, b])
                result = build_comparison([a, b])
                self.assertEqual(result["pairs"][0]["analysis"]["category"], expected)
                self.assertEqual(result["paired_analysis_summary"]["counts"][expected], 1)
                self.assertEqual([a, b], before)
