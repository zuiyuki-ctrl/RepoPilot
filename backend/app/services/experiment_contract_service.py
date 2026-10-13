"""实验定义、准备证据和任务配置之间的完整性检查；纯函数不读取工作区。"""
import hashlib
import json
import xml.etree.ElementTree as ET

from .test_report_parser import parse_test_report


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode()).hexdigest()


def contract_digest(preparation) -> str:
    return digest({"definition": preparation.definition.model_dump(mode="json"),
                   "case": preparation.case.model_dump(mode="json"),
                   "protected_test_file_hashes": preparation.protected_test_file_hashes,
                   "conditions": preparation.conditions, "baseline_test": preparation.baseline_test,
                   "repository_id": str(preparation.repository_id)})


def validate_definition(case, definition):
    if definition.decision_policy is not None and not any(
            p.case_id == case.case_id and p.case_version == case.case_version
            and p.repeat_index == definition.repeat_index for p in definition.decision_policy.expected_pairs):
        raise ValueError("Case/repeat is not in the declared decision batch")
    if case.task_type == "bug_fix" and not definition.acceptance.baseline_failure_tests:
        raise ValueError("Bug-fix acceptance requires declared baseline failure tests")
    modules = [p[:-3].replace("/", ".") for p in case.protected_test_files]
    for test in definition.acceptance.required_tests:
        if not any(test.classname == module or test.classname.startswith(module + ".") for module in modules):
            raise ValueError("Required test must belong to a protected test file")


def require_contract(preparation):
    expected = preparation.run_config.experiment_contract_sha256
    if preparation.definition is None:
        if expected is not None:
            raise ValueError("Experiment definition missing from sealed preparation")
        return
    validate_definition(preparation.case, preparation.definition)
    conditions = preparation.conditions or {}
    for field, value in (("runtime_fingerprint", conditions.get("runtime_fingerprint")),
                         ("index_fingerprint", conditions.get("index_fingerprint")),
                         ("test_image_id", (conditions.get("test_image") or {}).get("id")),
                         ("max_tool_calls", preparation.definition.max_tool_calls)):
        if getattr(preparation.run_config, field) != value:
            raise ValueError("Run configuration differs from sealed conditions: " + field)
    if expected is None or expected != contract_digest(preparation):
        raise ValueError("Experiment contract differs from frozen task configuration")


def test_outcomes(report) -> dict | None:
    if not isinstance(report, dict) or report.get("status") != "recorded" or not isinstance(report.get("xml"), str):
        return None
    verified = parse_test_report(report["xml"].encode("utf-8"))
    if verified != report:
        return None
    outcomes = {}
    for test in ET.fromstring(report["xml"]).iter("testcase"):
        key = (test.get("classname"), test.get("name"))
        if key in outcomes:
            return None
        outcomes[key] = "failed" if test.find("failure") is not None else (
            "errors" if test.find("error") is not None else "skipped" if test.find("skipped") is not None else "passed")
    return outcomes


def baseline_satisfies_rule(preparation) -> bool:
    baseline = preparation.baseline_test or {}
    before = test_outcomes(baseline.get("test_report"))
    return (before is not None and baseline.get("exit_code") == 1 and baseline.get("timed_out") is False
            and baseline.get("image") == preparation.run_config.test_image_id
            and baseline.get("timeout_seconds") == preparation.definition.test_timeout_seconds
            and baseline.get("repository_commit") == preparation.case.repository_commit
            and baseline.get("protected_test_file_hashes") == preparation.protected_test_file_hashes
            and isinstance(baseline.get("snapshot_hash"), str) and len(baseline["snapshot_hash"]) == 64
            and not any(v in ("errors", "skipped") for v in before.values())
            and all(before.get((t.classname, t.name)) == "failed"
                    for t in preparation.definition.acceptance.baseline_failure_tests))


def evaluate_acceptance(preparation, task_report, *, review=None) -> dict:
    result = {"outcome": "unknown", "reason": "legacy_definition_missing", "rule_version": None}
    if preparation.definition is None:
        return result
    require_contract(preparation)
    rule = preparation.definition.acceptance
    result.update(rule_version=rule.version, contract_sha256=preparation.run_config.experiment_contract_sha256)
    run = task_report.test_run
    if task_report.task.status == "failed":
        return {**result, "outcome": "not_passed", "reason": "execution_failed"}
    if run is None:
        return {**result, "reason": "final_test_missing"}
    result.update(test_run_id=str(run.id), report_sha256=(run.test_report or {}).get("sha256"))
    if run.image != preparation.run_config.test_image_id or run.timeout_seconds != preparation.definition.test_timeout_seconds:
        return {**result, "reason": "test_environment_drift"}
    if run.status != "finished" or run.timed_out or run.exit_code != 0 or run.error:
        return {**result, "outcome": "not_passed", "reason": "test_process_failed"}
    outcomes = test_outcomes(run.test_report)
    if outcomes is None:
        return {**result, "reason": "final_report_invalid_or_missing"}
    if any(outcomes.get((t.classname, t.name)) is None for t in rule.required_tests):
        return {**result, "reason": "required_tests_missing"}
    if any(value != "passed" for value in outcomes.values()):
        return {**result, "outcome": "not_passed", "reason": "tests_not_all_passed"}
    if preparation.case.task_type == "bug_fix":
        if not baseline_satisfies_rule(preparation):
            return {**result, "reason": "baseline_failure_evidence_missing"}
    if rule.manual_criteria:
        if review is None:
            return {**result, "reason": "manual_acceptance_review_required", "criteria": rule.manual_criteria}
        from ..schemas.experiment_definition import AcceptanceReview
        review = AcceptanceReview.model_validate(review)
        if (review.task_id != task_report.task.id or review.test_run_id != run.id
                or review.contract_sha256 != preparation.run_config.experiment_contract_sha256
                or review.test_report_sha256 != run.test_report["sha256"]
                or set(review.checked_criteria) != set(rule.manual_criteria)
                or task_report.task.completed_at is None or review.recorded_at < task_report.task.completed_at):
            raise ValueError("Acceptance review does not match the terminal evidence and declared criteria")
        return {**result, "outcome": "passed" if review.decision == "approved" else "not_passed",
                "reason": "manual_and_test_acceptance", "review": review.model_dump(mode="json")}
    return {**result, "outcome": "passed", "reason": "declared_test_contract_satisfied",
            "scope": "predeclared_automated_tests_only"}


def compare_conditions(left, right) -> dict:
    differences, missing = [], []
    if not left or not right:
        return {"status": "insufficient_evidence", "differences": [], "missing": ["paired_run"]}
    def flatten(value, prefix=""):
        result = {}
        if isinstance(value, dict):
            for key, child in value.items():
                result.update(flatten(child, f"{prefix}.{key}" if prefix else key))
        else:
            result[prefix] = value
        return result
    # 只比较输入条件；查询、上下文、结果及随机仓库/任务 ID 均不是控制变量。
    def inputs(row):
        conditions = row.get("conditions") or {}
        return {"definition": row.get("definition"), "case": row["case"],
                "protected_test_file_hashes": row.get("protected_test_file_hashes"),
                "runtime": conditions.get("runtime"), "index_fingerprint": conditions.get("index_fingerprint"),
                "test_image_id": (conditions.get("test_image") or {}).get("id"),
                "max_tool_calls": row["run_config"]["max_tool_calls"], "max_retries": row.get("max_retries"),
                "actual_test_image": (row.get("test") or {}).get("image"),
                "actual_timeout": (row.get("test") or {}).get("timeout_seconds")}
    a, b = flatten(inputs(left)), flatten(inputs(right))
    for field in sorted(a.keys() | b.keys()):
        if a.get(field) is None or b.get(field) is None:
            missing.append(field)
        elif a[field] != b[field]:
            differences.append({"field": field, "baseline": a[field], "candidate": b[field]})
    for row in (left, right):
        conditions = row.get("conditions") or {}
        runtime = conditions.get("runtime") or {}
        for field in ("chat_model", "embedding_model", "embedding_dimensions", "chat_parameters",
                      "prompt_templates_sha256", "tool_definitions_sha256", "context_budget_chars",
                      "implementation_sha256", "provider_internal_version"):
            if not runtime.get(field):
                missing.append("runtime." + field)
        if not conditions.get("runtime") or not row["run_config"].get("experiment_contract_sha256"):
            missing.append("frozen_contract")
        if row.get("definition") and row.get("test"):
            for field, expected in (("image", (conditions.get("test_image") or {}).get("id")),
                                    ("timeout_seconds", row["definition"]["test_timeout_seconds"])):
                actual = row["test"].get(field)
                if expected is not None and actual != expected:
                    differences.append({"field": row["strategy"] + ".test." + field,
                                        "expected": expected, "actual": actual})
    return {"status": "different" if differences else "insufficient_evidence" if missing else "recorded_conditions_match",
            "differences": differences, "missing": sorted(set(missing)),
            "note": "相同的已记录条件不代表统计显著、供应商内部版本可复现或自动发布许可"}
