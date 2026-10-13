"""固定口径的资源差额与批次门槛；纯历史数据分析，不执行采用或发布。"""
from datetime import datetime
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from ..schemas.experiment_decision import DecisionPolicy, DecisionReview
from .experiment_contract_service import digest


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except InvalidOperation:
        return None


def delta(baseline, candidate):
    a, b = number(baseline), number(candidate)
    return {"baseline": str(a) if a is not None else None, "candidate": str(b) if b is not None else None,
            "absolute": str(b - a) if a is not None and b is not None else None,
            "relative_percent": str((b - a) / a * 100) if a is not None and b is not None and a > 0 else None,
            "status": "missing" if a is None or b is None else "baseline_zero" if a == 0 else "recorded"}


def resource_values(row):
    metrics = (row or {}).get("metrics") or {}
    resources = metrics.get("resources") or {}
    cost = (row or {}).get("cost") or {}
    return {"tokens": resources.get("total_tokens") if resources.get("status") == "complete"
            and resources.get("scope_complete") is True else None,
            "wall_time_ms": metrics.get("wall_clock_ms") if metrics.get("started") is True else None,
            "estimated_cost": cost.get("total") if cost.get("status") == "complete" and cost.get("pricing") else None}


def pair_resources(pair):
    a, b = pair["runs"].get("vector"), pair["runs"].get("hybrid")
    left, right = resource_values(a), resource_values(b)
    result = {key: delta(left[key], right[key]) for key in left}
    ca, cb = (a or {}).get("cost") or {}, (b or {}).get("cost") or {}
    same_price = bool(ca.get("pricing") and ca.get("pricing") == cb.get("pricing")
                      and ca.get("currency") and ca.get("currency") == cb.get("currency"))
    if not same_price:
        result["estimated_cost"] = {**delta(None, None), "status": "pricing_missing_or_different"}
    result["estimated_cost"]["currency"] = ca.get("currency") if same_price else None
    for metric in result.values():
        metric["valid_pairs"] = 1 if metric["absolute"] is not None else 0
        metric["coverage"] = float(metric["valid_pairs"])
    result["scope"] = "task_chat_and_query_embedding; preparation_excluded; wall_time_includes_human_wait"
    result["comparison_eligible"] = pair["analysis"]["category"] not in ("undecided", "non_comparable")
    return result


def build_decision(pairs, *, policy=None, review=None):
    rows = [r for pair in pairs for r in pair["runs"].values()]
    source = "exploratory" if policy is not None else "not_configured"
    notes = []
    if policy is None:
        frozen = [(r.get("definition") or {}).get("decision_policy") for r in rows]
        if frozen and all(p is not None and p == frozen[0] for p in frozen):
            policy, source = frozen[0], "preregistered"
        elif any(p is not None for p in frozen):
            notes.append("frozen_policies_missing_or_different")
    rule = DecisionPolicy.model_validate(policy) if policy is not None else None
    policy_data = rule.model_dump(mode="json") if rule else None
    checks = []

    def check(name, observed, threshold, passed):
        checks.append({"name": name, "observed": observed, "threshold": threshold,
                       "status": "unknown" if passed is None else "pass" if passed else "fail"})

    eligible = [p for p in pairs if p["analysis"]["category"] not in ("undecided", "non_comparable")
                and all((p["runs"][s].get("metrics") or {}).get("started") is True for s in ("vector", "hybrid"))]
    n, total = len(eligible), len(pairs)
    coverage = n / total if total else None
    regressions = sum(p["analysis"]["category"] == "regressed" for p in eligible)
    quality = (sum(p["analysis"]["category"] == "improved" for p in eligible) - regressions) * 100 / n if n else None
    aggregates = {}
    for key in ("tokens", "estimated_cost", "wall_time_ms"):
        values = [p["resource_deltas"][key] for p in eligible
                  if p["resource_deltas"][key]["absolute"] is not None]
        prices = [(r.get("cost") or {}).get("pricing") for p in eligible for r in p["runs"].values()]
        if key == "estimated_cost" and (not prices or not prices[0] or any(p != prices[0] for p in prices)):
            values = []
        aggregate = delta(sum(Decimal(v["baseline"]) for v in values) / len(values) if values else None,
                          sum(Decimal(v["candidate"]) for v in values) / len(values) if values else None)
        aggregates[key] = {**aggregate, "valid_pairs": len(values),
                           "coverage": len(values) / total if total else None,
                           "currency": next((v.get("currency") for v in values), None),
                           "scope": "means_of_same_complete_comparable_started_pairs"}
    if rule:
        expected = {(p.case_id, p.case_version, p.repeat_index) for p in rule.expected_pairs}
        actual = {(p["case_id"], p["case_version"], p["repeat_index"]) for p in pairs}
        check("declared_batch", total, len(expected), True if actual == expected else None)
        if actual != expected:
            notes.append("missing_or_extra_declared_pairs")
        if source == "preregistered":
            valid_time = all(r.get("prepared_at") and datetime.fromisoformat(r["prepared_at"]).tzinfo
                             and rule.declared_at <= datetime.fromisoformat(r["prepared_at"]) for r in rows)
            check("policy_frozen_before_preparation", bool(valid_time), True, True if valid_time else None)
        check("minimum_pairs", n, rule.min_pairs, n >= rule.min_pairs)
        check("classification_coverage", coverage, rule.min_classification_coverage,
              coverage >= rule.min_classification_coverage if coverage is not None else None)
        # 不让低覆盖率门槛把条件缺失涂成绿色；展示部分结果，但不输出全面符合。
        check("all_pair_conditions_and_start_evidence", n, total, True if total and n == total else None)
        check("regressions", regressions, rule.max_regressions, regressions <= rule.max_regressions)
        check("quality_delta_pp", quality, rule.min_quality_delta_pp,
              quality >= rule.min_quality_delta_pp if quality is not None else None)
        for key, cap in (("tokens", rule.max_token_increase_percent),
                         ("estimated_cost", rule.max_cost_increase_percent),
                         ("wall_time_ms", rule.max_wall_time_increase_percent)):
            if cap is None:
                continue
            aggregate = aggregates[key]
            value = aggregate["relative_percent"]
            sufficient = (aggregate["coverage"] is not None and aggregate["coverage"] >= rule.min_resource_coverage)
            if key == "estimated_cost" and aggregate["currency"] != rule.cost_currency:
                sufficient = False
            check(key + "_relative_percent", value, cap,
                  Decimal(value) <= Decimal(str(cap)) if sufficient and value is not None else None)
        # 未决/条件缺失优先，保留明确失败的单项检查供复核，但不基于不完整批次宣称优劣。
        verdict = ("insufficient_evidence" if any(c["status"] == "unknown" for c in checks) else
                   "does_not_meet_batch_rules" if any(c["status"] == "fail" for c in checks) else "meets_batch_rules")
    else:
        verdict = "insufficient_evidence"
        notes.append("decision_policy_not_configured")
    result = {"version": 1, "verdict": verdict, "policy_source": source, "policy": policy_data,
              "checks": checks, "missing_reasons": notes, "resource_deltas": aggregates,
              "quality": {"delta_pp": quality, "classified_started_pairs": n, "selected_pairs": total,
                          "coverage": coverage, "regressions": regressions,
                          "scope": "comparable_decided_started_pairs_only_not_whole_batch_success_rate"},
              "next_steps": (["先补齐冻结条件、验收和启动/资源证据，再按声明批次继续实验。"] if verdict == "insufficient_evidence"
                             else ["逐例复核退化及未达门槛项，提出单变量实验；暂不自动采用。"] if verdict == "does_not_meet_batch_rules"
                             else ["仅满足本批门槛；人工复核适用范围，并用预声明的更多任务验证泛化。"]),
              "limitations": ["事后门槛标为探索性，不能追认为预注册验收。", "资源差额仅使用同对完整样本；成本是估算，墙钟包含人工等待。",
                              "本批符合不证明统计显著或可泛化；不自动采用、发布或推荐 Reranker。"],
              "review": None}
    bound_pairs = deepcopy(pairs)
    for pair in bound_pairs:
        for row in pair["runs"].values():
            row["artifacts"] = {key: artifact.get("sha256") if artifact else None
                                for key, artifact in row.get("artifacts", {}).items()}
    result["decision_sha256"] = digest({"decision": result, "pairs": bound_pairs})
    if review is not None:
        checked = DecisionReview.model_validate(review)
        dates = [r.get("completed_at") for r in rows]
        if (checked.decision_sha256 != result["decision_sha256"] or not dates or not all(dates)
                or any(datetime.fromisoformat(d).tzinfo is None or checked.recorded_at < datetime.fromisoformat(d) for d in dates)):
            raise ValueError("Decision review differs from this batch or predates terminal evidence")
        result["review"] = checked.model_dump(mode="json")
    return result
