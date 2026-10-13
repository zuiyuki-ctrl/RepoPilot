"""Synthetic offline decision fixtures; never persisted as real experiment outcomes."""
from copy import deepcopy
import unittest

from backend.app.schemas.experiment_decision import DecisionPolicy
from backend.app.schemas.experiment_definition import ExperimentDefinition
from backend.app.services.experiment_decision_service import build_decision, delta, pair_resources


def policy():
    return dict(version="synthetic-v1", declared_at="2026-10-01T00:00:00Z",
        expected_pairs=[dict(case_id="synthetic", case_version="v1", repeat_index=1)],
        min_pairs=1, min_classification_coverage=1.0, max_regressions=0, min_quality_delta_pp=0.0,
        min_resource_coverage=1.0, max_token_increase_percent=20.0)


def pair(category="improved", frozen=True):
    runs = {}
    for strategy in ("vector", "hybrid"):
        runs[strategy] = dict(experiment_id="synthetic-" + strategy,
            definition={"decision_policy": policy()} if frozen else {},
            prepared_at="2026-10-02T00:00:00+00:00", completed_at="2026-10-03T00:00:00+00:00",
            metrics={"started": True, "resources": {"scope_complete": True, "status": "complete",
                "total_tokens": 100 if strategy == "vector" else 110}, "wall_clock_ms": 1000},
            artifacts={"report": {"path": "local", "sha256": strategy}})
    result = dict(case_id="synthetic", case_version="v1", repeat_index=1,
        analysis={"category": category}, runs=runs)
    result["resource_deltas"] = pair_resources(result)
    return result


class ExperimentDecisionTests(unittest.TestCase):
    def test_preregistered_rule_and_independent_review(self):
        rows = [pair()]
        before = deepcopy(rows)
        result = build_decision(rows)
        self.assertEqual(result["verdict"], "meets_batch_rules")
        self.assertEqual(result["policy_source"], "preregistered")
        self.assertEqual(result["quality"]["delta_pp"], 100)
        self.assertEqual(result["resource_deltas"]["tokens"]["relative_percent"], "10.0")
        review = dict(decision_sha256=result["decision_sha256"], reviewer="synthetic-reviewer",
                      recorded_at="2026-10-04T00:00:00Z", action="continue_experiment", rationale="Synthetic limited scope")
        checked = build_decision(rows, review=review)
        self.assertEqual(checked["review"]["action"], "continue_experiment")
        self.assertEqual(checked["verdict"], result["verdict"])
        self.assertEqual(rows, before)
        rows[0]["runs"]["vector"]["artifacts"]["report"]["path"] = "another-computer"
        self.assertEqual(build_decision(rows, review=review)["decision_sha256"], result["decision_sha256"])
        rows[0]["runs"]["vector"]["artifacts"]["report"]["sha256"] = "changed"
        with self.assertRaises(ValueError):
            build_decision(rows, review=review)

    def test_regression_and_resource_breach(self):
        self.assertEqual(build_decision([pair("regressed")])["verdict"], "does_not_meet_batch_rules")
        item = pair()
        item["runs"]["hybrid"]["metrics"]["resources"]["total_tokens"] = 121
        item["resource_deltas"] = pair_resources(item)
        self.assertEqual(build_decision([item])["verdict"], "does_not_meet_batch_rules")

    def test_unknown_conditions_start_and_missing_pairs_never_green(self):
        for category in ("undecided", "non_comparable"):
            self.assertEqual(build_decision([pair(category)])["verdict"], "insufficient_evidence")
        item = pair()
        item["runs"]["vector"]["metrics"]["started"] = None
        self.assertEqual(build_decision([item])["verdict"], "insufficient_evidence")
        self.assertEqual(build_decision([], policy=policy())["verdict"], "insufficient_evidence")
        item = pair()
        item["repeat_index"] = 2
        self.assertIn("missing_or_extra_declared_pairs", build_decision([item])["missing_reasons"])

    def test_posthoc_and_missing_mixed_or_late_rules(self):
        item = pair(frozen=False)
        self.assertEqual(build_decision([item])["verdict"], "insufficient_evidence")
        self.assertEqual(build_decision([item], policy=policy())["policy_source"], "exploratory")
        item = pair()
        item["runs"]["hybrid"]["definition"] = {}
        self.assertEqual(build_decision([item])["verdict"], "insufficient_evidence")
        item = pair()
        item["runs"]["vector"]["prepared_at"] = "2026-09-01T00:00:00Z"
        self.assertEqual(build_decision([item])["verdict"], "insufficient_evidence")

    def test_resources_missing_zero_partial_nonfinite_and_currency(self):
        for value in (None, True, "NaN", "Infinity", -1):
            with self.subTest(value=value):
                self.assertEqual(delta(value, 10)["status"], "missing")
        self.assertIsNone(delta(0, 1)["relative_percent"])
        item = pair()
        item["runs"]["vector"]["metrics"]["resources"]["status"] = "partial"
        item["resource_deltas"] = pair_resources(item)
        self.assertEqual(build_decision([item])["verdict"], "insufficient_evidence")
        item = pair()
        for row in item["runs"].values():
            row["cost"] = dict(status="complete", total="0.01", currency="USD", pricing={"version": "synthetic"})
        item["resource_deltas"] = pair_resources(item)
        rule = {**policy(), "max_cost_increase_percent": 0, "cost_currency": "CNY"}
        self.assertEqual(build_decision([item], policy=rule)["verdict"], "insufficient_evidence")
        item["runs"]["hybrid"]["cost"]["pricing"] = {"version": "different"}
        self.assertEqual(pair_resources(item)["estimated_cost"]["status"], "pricing_missing_or_different")

    def test_invalid_policy_and_review(self):
        for change in ({"min_pairs": 2}, {"min_resource_coverage": 0}, {"min_quality_delta_pp": float("nan")},
                       {"expected_pairs": policy()["expected_pairs"] * 2}, {"max_cost_increase_percent": 20}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                DecisionPolicy.model_validate({**policy(), **change})
        rows = [pair()]
        review = dict(decision_sha256=build_decision(rows)["decision_sha256"], reviewer="tester",
            recorded_at="2020-01-01T00:00:00Z", action="adopt_candidate", rationale="synthetic")
        with self.assertRaises(ValueError):
            build_decision(rows, review=review)

    def test_legacy_definition_serialization_unchanged(self):
        value = ExperimentDefinition(suite_id="synthetic", suite_version="v1", config_version="v1", repeat_index=1,
            acceptance={"version": "v1", "required_tests": [{"classname": "tests.test_example", "name": "test_it"}]})
        self.assertNotIn("decision_policy", value.model_dump(mode="json"))
        value.decision_policy = DecisionPolicy.model_validate(policy())
        self.assertEqual(value.model_dump(mode="json")["decision_policy"]["version"], "synthetic-v1")


if __name__ == "__main__":
    unittest.main()
