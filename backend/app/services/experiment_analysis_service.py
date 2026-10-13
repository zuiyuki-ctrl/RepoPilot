"""离线分析已关联的历史证据；不访问工作区，也不将观测阶段当成根因。"""
from datetime import datetime

from ..schemas.failure_analysis import FailureReview
from .experiment_contract_service import digest, test_outcomes


PAIR_CATEGORIES = ("stayed_success", "improved", "regressed", "both_not_success",
                   "undecided", "non_comparable")


def analyze_pair(baseline, candidate, comparability: dict, *, observed_differences=()) -> dict:
    """仅消费第 4 天验收/条件结果，不另设成功判据。"""
    outcomes = {name: (row.get("acceptance") or {}).get("outcome", "unknown") if row else "unknown"
                for name, row in (("baseline", baseline), ("candidate", candidate))}
    tests = {name: (row.get("test") or {}).get("process_passed") if row else None
             for name, row in (("baseline", baseline), ("candidate", candidate))}
    category, reason = "undecided", "acceptance_unknown"
    if not baseline or not candidate:
        reason = "paired_run_missing"
    elif comparability["status"] == "different" or observed_differences:
        category, reason = "non_comparable", "recorded_conditions_differ"
    elif comparability["status"] != "recorded_conditions_match":
        reason = "comparability_evidence_insufficient"
    elif all(value in ("passed", "not_passed") for value in outcomes.values()):
        category = {("passed", "passed"): "stayed_success",
                    ("not_passed", "passed"): "improved",
                    ("passed", "not_passed"): "regressed",
                    ("not_passed", "not_passed"): "both_not_success"}[
                        outcomes["baseline"], outcomes["candidate"]]
        reason = "declared_acceptance_and_recorded_conditions"
    return {"category": category, "reason": reason, "acceptance_outcomes": outcomes,
            "test_process_outcomes": tests,
            "both_test_processes_passed": all(value is True for value in tests.values()),
            "scope": "predeclared_acceptance_under_recorded_conditions",
            "note": "测试进程通过不等于验收成功；配对变化不证明因果关系或总体收益"}


def summarize_pairs(pairs: list[dict]) -> dict:
    counts = {category: sum(pair["analysis"]["category"] == category for pair in pairs)
              for category in PAIR_CATEGORIES}
    assessed = sum(counts[key] for key in PAIR_CATEGORIES[:4])
    return {"primary_pairs": len(pairs), "classified_pairs": assessed, "counts": counts,
            "classification_coverage": assessed / len(pairs) if pairs else None,
            "scope": "explicit_primary_pairs_only",
            "note": "额外尝试不参与配对统计；未决与不可比保留，不将已判定子集当作批次成功率"}


def analyze_failure(row: dict, *, review=None) -> dict:
    """结构化失败事实、候选解释和人工复核分别保存。摘要文字不用于推断类别。"""
    failure, test = row.get("failure") or {}, row.get("test") or {}
    acceptance = row.get("acceptance") or {}
    evidence, facts, hypotheses = [], [], []
    outcomes = None

    def add(identifier, source, value):
        evidence.append({"id": identifier, "source": source, "value": value})

    if row.get("preparation_status") in ("error", "preparing"):
        add("preparation", "preparation", {"stage": row.get("preparation_stage"),
            "status": row["preparation_status"], "error_type": row.get("preparation_error_type")})
    if failure:
        add("terminal_event", "report.failure", failure)
        facts.append({"kind": "task_terminated", "evidence_ids": ["terminal_event"]})
    elif row.get("completion_event_sequence") is not None:
        add("terminal_event", "report.completion_event_sequence",
            {"sequence": row["completion_event_sequence"], "event_type": "TASK_COMPLETED"})
    if test:
        add("final_test", "report.test_run", {key: test.get(key) for key in (
            "id", "status", "exit_code", "timed_out", "error", "snapshot_hash")})
        evidence[-1]["value"]["sha256"] = digest(test)
        # 原始结构化报告重新校验；不相信导出的计数字段或 stdout 文本。
        outcomes = test_outcomes(test.get("test_report"))
        if outcomes is not None:
            add("test_report", "report.test_run.test_report", {
                "sha256": test["test_report"]["sha256"],
                "nonpassing_tests": [{"classname": name[0], "name": name[1], "outcome": outcome}
                                     for name, outcome in outcomes.items() if outcome != "passed"]})
            for outcome, kind in (("failed", "test_failure_reported"), ("errors", "test_error_reported"),
                                  ("skipped", "test_skipped")):
                if outcome in outcomes.values():
                    facts.append({"kind": kind, "evidence_ids": ["final_test", "test_report"]})
        elif test.get("test_report"):
            facts.append({"kind": "structured_test_report_unusable", "evidence_ids": ["final_test"]})
        if test.get("timed_out"):
            facts.append({"kind": "test_timeout", "evidence_ids": ["final_test"]})
        elif test.get("error") or test.get("exit_code") not in (None, 0):
            facts.append({"kind": "test_process_not_passed", "evidence_ids": ["final_test"]})
    if row.get("final_diff") is not None:
        diff = row["final_diff"]
        add("final_diff", "report.final_diff", {"sha256": digest(diff),
            "changed_files": diff.get("changed_files"), "untracked_files": diff.get("untracked_files"),
            "truncated": diff.get("truncated"), "scope": "terminal_saved_diff_only"})
    if acceptance:
        add("acceptance", "comparison.acceptance", acceptance)
    for query in (row.get("retrieval") or {}).get("queries", []):
        sequence = query.get("event_sequence")
        if type(sequence) is int and sequence > 0:
            add(f"retrieval:{sequence}", "evidence.events.RETRIEVAL_COMPLETED", query)
    # 使用终态报告的全程请求观测；没有时才使用有明确范围限制的检索轨迹切片。
    metrics = row.get("metrics") or {}
    request_source = ("report.metrics.request_observations" if metrics.get("request_observations") is not None
                      else "evidence.request_observations")
    requests = metrics.get("request_observations")
    if requests is None:
        requests = row.get("request_observations") or []
    request_stages = []
    for request in requests:
        observation = request.get("observation") or {}
        if (request.get("completeness") != "recorded" or observation.get("operation_status") != "failed"
                or not request.get("call_id") or observation.get("call_id") != request["call_id"]):
            continue
        identifier = f"request:{request.get('kind')}:{request.get('phase')}:{request['call_id']}"
        add(identifier, request_source, {"call_id": request["call_id"], "kind": request.get("kind"),
            "phase": request.get("phase"), "finished_sequences": request.get("finished_sequences"),
            "failure_stage": observation.get("failure_stage"), "error_type": observation.get("error_type")})
        facts.append({"kind": "request_operation_failed", "evidence_ids": [identifier]})
        if request.get("phase"):
            request_stages.append(request["phase"])
    failed = (row.get("status") in ("failed", "preparation_error")
              or acceptance.get("outcome") == "not_passed"
              or any(f["kind"] in ("test_failure_reported", "test_error_reported", "test_timeout",
                                   "test_process_not_passed") for f in facts))
    stage, primary = "unknown", "UNKNOWN"
    if row.get("status") == "preparation_error":
        stage = "preparation"
        facts.append({"kind": "preparation_failed", "evidence_ids": ["preparation"]})
    elif failure.get("event_type") == "REFLECTION_FINISHED":
        stage = "recovery"
        facts.append({"kind": "reflection_stopped", "evidence_ids": ["terminal_event"]})
        if failure.get("reflection"):
            hypotheses.append({"source": "model_reflection", "category": "UNKNOWN",
                "statement": failure["reflection"]["diagnosis"], "evidence_ids": ["terminal_event"],
                "review_status": "unreviewed"})
    elif failure.get("reason_code") == "retry_budget_exhausted":
        stage, primary = "recovery", "BUDGET_EXCEEDED"
        facts.append({"kind": "retry_budget_exhausted", "evidence_ids": ["terminal_event"]})
    # 关联的历史测试只说明在测试中观察到了问题，不证明任务终止发生在该阶段。
    observed_stages = request_stages + ([stage] if stage != "unknown" else [])
    if any(f["kind"].startswith("test_") for f in facts):
        observed_stages.append("testing")
    if acceptance.get("outcome") == "not_passed":
        facts.append({"kind": "acceptance_not_passed", "evidence_ids": ["acceptance"]})
        observed_stages.append("acceptance")
    missing = []
    if not test:
        missing.append("final_test")
    elif outcomes is None:
        missing.append("usable_structured_test_report")
    if row.get("final_diff") is None:
        missing.append("terminal_saved_diff")
    if not failure and not row.get("completion_event_sequence"):
        missing.append("terminal_event")
    if not row.get("retrieval") or row["retrieval"].get("trace_status") == "not_recorded":
        missing.append("retrieval_trace")
    elif row["retrieval"].get("trace_status") == "partial":
        missing.append("complete_retrieval_trace")
    snapshot = {"analysis_version": 1, "task_id": row.get("task_id"), "experiment_id": row.get("experiment_id"),
                "contract_sha256": (row.get("run_config") or {}).get("experiment_contract_sha256"),
                "status": row.get("status"), "completed_at": row.get("completed_at"),
                "evidence": evidence, "retrieval": row.get("retrieval")}
    result = {"version": 1, "status": "failure_observed" if failed else (
                "no_failure_observed" if row.get("status") == "completed" else "evidence_incomplete"),
              "analysis_sha256": digest(snapshot), "termination_stage": stage,
              "observed_stages": sorted(set(observed_stages)), "facts": facts, "evidence": evidence,
              "primary_category": primary, "secondary_categories": [], "source": "rule",
              "classification_scope": "termination_reason_not_proven_root_cause",
              "root_cause_status": "unknown", "hypotheses": hypotheses,
              "review_status": "unreviewed" if failed else "not_requested", "review": None,
              "missing_evidence": missing,
              "limitations": ["测试 failure/error/超时不自动证明基础设施、检索或推理根因",
                              "反思诊断是模型假设，不是人工确认；Top K 与候选计数不证明候选被排序排除",
                              "只使用保存的历史证据；失败报告缺 Diff 时不读取当前工作区补齐"]}
    if review is not None:
        checked = FailureReview.model_validate(review)
        completed_at = row.get("completed_at")
        available = {item["id"] for item in evidence}
        if (not failed or str(checked.task_id) != row.get("task_id")
                or checked.analysis_sha256 != result["analysis_sha256"]
                or not completed_at or datetime.fromisoformat(completed_at).tzinfo is None
                or checked.recorded_at < datetime.fromisoformat(completed_at)
                or not set(checked.evidence_ids) <= available):
            raise ValueError("Failure review differs from the terminal analysis evidence")
        result.update(primary_category=checked.primary_category,
                      secondary_categories=checked.secondary_categories, source="manual",
                      classification_scope="human_assessment_not_automatic_proof",
                      root_cause_status="unknown" if checked.primary_category == "UNKNOWN" else "human_assessed",
                      review_status="reviewed",
                      review=checked.model_dump(mode="json"))
        result["hypotheses"].append({"source": "manual", "category": checked.primary_category,
            "statement": checked.hypothesis, "evidence_ids": checked.evidence_ids, "review_status": "reviewed"})
    return result
