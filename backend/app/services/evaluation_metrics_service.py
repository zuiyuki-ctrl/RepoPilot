"""纯函数评测：保留未知、来源与覆盖率，绝不以进程通过代替需求验收。"""
from collections import Counter
from decimal import Decimal
from types import SimpleNamespace

from .request_observation_service import collect_request_observations
from .test_report_parser import parse_test_report


def preparation_resources(records: list[dict] | None, *, preparation_complete: bool) -> dict | None:
    if records is None:
        return None
    events = []
    for sequence, record in enumerate(records, 1):
        suffix = {"started": "STARTED", "completed": "COMPLETED", "failed": "FAILED"}[record["status"]]
        obs = record["observation"]
        events.append(SimpleNamespace(sequence=sequence, node_name="index_embedding",
            event_type="EMBEDDING_CALL_" + suffix,
            payload={"call_id": obs["call_id"], "scope": "preparation_index", "model_observation": obs}))
    rows = collect_request_observations(events)
    return {"scope": "preparation_index", "resources": resource_metrics(rows, complete_scope=preparation_complete),
            "request_observations": rows}


def test_metrics(run) -> dict:
    result = {"source": "TestRun.test_report", "test_run_id": str(run.id) if run else None,
              "counts": None, "pass_rate": None, "report_status": "not_recorded"}
    if run is None or not run.test_report:
        return result
    report = run.test_report
    result["report_status"] = report.get("status", "invalid")
    xml = report.get("xml")
    if report.get("status") != "recorded" or not isinstance(xml, str):
        return result
    verified = parse_test_report(xml.encode("utf-8"))
    if verified != report:
        return {**result, "report_status": "inconsistent"}
    counts = verified["counts"]
    total = sum(counts.values())
    if run.timed_out or run.status != "finished":
        return {**result, "report_status": "incomplete"}
    return {**result, "counts": counts, "report_sha256": verified["sha256"],
            "pass_rate": counts["passed"] / total if total else None,
            "count_unit": "junit_testcase_records"}


def resource_metrics(rows: list[dict], *, complete_scope: bool) -> dict:
    # call_id 是请求身份；重复身份不能择优选一条计入。
    ids = Counter(row["call_id"] for row in rows)
    candidates = []
    unattempted = 0
    for row in rows:
        obs = row.get("observation")
        if row.get("completeness") == "recorded" and ids[row["call_id"]] == 1 and isinstance(obs, dict):
            if obs.get("request_attempted") is False:
                unattempted += 1
                continue
            candidates.append(obs if obs.get("request_attempted") is True else None)
        else:
            candidates.append(None)
    known = [obs for obs in candidates if obs and obs.get("usage_status") == "complete"
             and type(obs.get("usage", {}).get("total_tokens")) is int
             and obs["usage"]["total_tokens"] >= 0]
    durations = [obs["duration_ms"] for obs in candidates if obs
                 and type(obs.get("duration_ms")) is int and obs["duration_ms"] >= 0]
    complete = complete_scope and len(known) == len(candidates)
    fields = {}
    for field in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens"):
        values = [obs["usage"][field] for obs in known
                  if type(obs["usage"].get(field)) is int and obs["usage"][field] >= 0]
        fields[field] = {"known_subtotal": sum(values), "recorded_calls": len(values)}
    return {"scope_complete": complete_scope, "observed_calls": len(rows),
            "known_not_attempted": unattempted,
            "attempted_calls": sum(obs is not None for obs in candidates),
            "unknown_attempt_calls": sum(obs is None for obs in candidates),
            "usage_known_calls": len(known), "usage_expected_calls": len(candidates),
            "usage_coverage": len(known) / len(candidates) if candidates else (1.0 if complete_scope else None),
            "known_total_tokens": sum(obs["usage"]["total_tokens"] for obs in known),
            "total_tokens": sum(obs["usage"]["total_tokens"] for obs in known) if complete else None,
            "token_fields": fields,
            "request_duration_ms_known_sum": sum(durations),
            "duration_known_calls": len(durations),
            "duration_note": "请求耗时之和，不是运行墙钟时间；不累加嵌套工具 span",
            "status": "complete" if complete else "partial"}


def estimate_cost(rows: list[dict], prices: dict | None, *, complete_scope: bool) -> dict:
    """价格由用户显式提供；输入价包含缓存时 flat，否则必须提供缓存用量。"""
    from ..schemas.pricing import PricingSnapshot
    if prices is not None:
        prices = PricingSnapshot.model_validate(prices).model_dump(mode="json")
    result = {"kind": "estimate", "pricing": prices, "known_subtotal": "0",
              "total": None, "priced_calls": 0, "unpriced_calls": 0}
    if prices is None:
        return {**result, "status": "pricing_missing", "known_subtotal": None}
    subtotal = Decimal(0)
    ids = Counter(row["call_id"] for row in rows)
    for row in rows:
        obs = row.get("observation") or {}
        if obs.get("request_attempted") is False and row.get("completeness") == "recorded":
            continue
        model = obs.get("response_model") or obs.get("requested_model")
        rate = prices["models"].get(model)
        usage = obs.get("usage", {})
        valid = row.get("completeness") == "recorded" and ids[row["call_id"]] == 1
        if not valid or not rate or obs.get("usage_status") != "complete" or obs.get("request_attempted") is not True:
            result["unpriced_calls"] += 1
            continue
        input_tokens = usage.get("input_tokens")
        output_tokens = 0 if row.get("kind") == "embedding" else usage.get("output_tokens")
        cached = usage.get("cached_input_tokens") if rate.get("cached_input_per_million") is not None else 0
        if any(type(n) is not int or n < 0 for n in (input_tokens, output_tokens, cached)) or cached > input_tokens:
            result["unpriced_calls"] += 1
            continue
        amount = Decimal(input_tokens - cached) * Decimal(str(rate["input_per_million"]))
        amount += Decimal(output_tokens) * Decimal(str(rate["output_per_million"]))
        if cached:
            amount += Decimal(cached) * Decimal(str(rate["cached_input_per_million"]))
        subtotal += amount / Decimal(1_000_000)
        result["priced_calls"] += 1
    complete = complete_scope and result["unpriced_calls"] == 0
    return {**result, "currency": prices["currency"], "known_subtotal": str(subtotal),
            "total": str(subtotal) if complete else None, "status": "complete" if complete else "partial"}


def build_run_metrics(task, run, events, *, terminal_sequence: int) -> dict:
    sequences = [event.sequence for event in events]
    complete = sequences == list(range(1, terminal_sequence + 1))
    rows = collect_request_observations(events)
    started = any(event.event_type == "TASK_STARTED" for event in events)
    instrumented = any(event.event_type == "TASK_STARTED" and
                       event.payload.get("observation_protocol_version") == 1 for event in events)
    identifiable = all(isinstance(event.payload.get("call_id"), str) and event.payload["call_id"]
        for event in events if event.event_type.startswith(("MODEL_CALL_", "EMBEDDING_CALL_")))
    resource_scope = complete and instrumented and identifiable
    tests = test_metrics(run)
    # 当前旧用例只有文件范围，没有版本化验收定义/基线失败/人工语义复核。
    # 负向结果可确定未通过；正向结果不能据此冒充需求成功。
    outcome = "not_passed" if task.status == "failed" or (run and (run.timed_out or run.exit_code not in (None, 0))) else "unknown"
    wall_ms = None
    if task.started_at and task.completed_at:
        delta = (task.completed_at - task.started_at).total_seconds() * 1000
        wall_ms = int(delta) if delta >= 0 else None
    return {"version": 1, "source": "task_events_through_terminal", "terminal_sequence": terminal_sequence,
            "event_scope_complete": complete, "started": True if started else (False if complete else None),
            "request_observations": rows,
            "resources": resource_metrics(rows, complete_scope=resource_scope),
            "resources_by_kind": {kind: resource_metrics([r for r in rows if r["kind"] == kind],
                complete_scope=resource_scope) for kind in ("chat", "embedding")},
            "resources_by_phase": {phase: resource_metrics([r for r in rows if r["phase"] == phase],
                complete_scope=resource_scope) for phase in sorted({r["phase"] for r in rows})},
            "cost": estimate_cost(rows, None, complete_scope=resource_scope),
            "wall_clock_ms": wall_ms, "wall_clock_includes_human_wait": True,
            "human_wait_ms": None, "tests": tests,
            "acceptance": {"outcome": outcome, "rule_version": "evidence-conservative-v1",
                           "reason": "execution_failed" if outcome == "not_passed" else "versioned_acceptance_evidence_missing",
                           "source_test_run_id": tests["test_run_id"]}}


def aggregate_metrics(metrics: list[dict | None]) -> dict:
    known = [m for m in metrics if m is not None]
    started = [m for m in known if m.get("started") is True]
    passed = sum(m["acceptance"]["outcome"] == "passed" for m in started)
    unknown = sum(m["acceptance"]["outcome"] == "unknown" for m in started)
    counts = [m["tests"]["counts"] for m in known if m["tests"]["counts"] is not None]
    total = sum(sum(c.values()) for c in counts)
    def average(values):
        return {"mean": sum(values) / len(values) if values else None,
                "valid_runs": len(values), "coverage": len(values) / len(metrics) if metrics else None}
    token_values = [m["resources"]["total_tokens"] for m in known if m["resources"]["total_tokens"] is not None]
    wall_values = [m["wall_clock_ms"] for m in known if m["wall_clock_ms"] is not None]
    return {"runs": len(metrics), "metrics_recorded_runs": len(known), "started_runs": len(started),
            "total_tokens": average(token_values), "wall_clock_ms_including_human_wait": average(wall_values),
            "start_unknown_runs": len(metrics) - sum(m.get("started") is not None for m in known),
            "acceptance_passed_runs": passed, "acceptance_unknown_started_runs": unknown,
            "provisional_success_rate": passed / len(started) if started else None,
            "final_success_rate": passed / len(started) if started and not unknown and len(known) == len(metrics)
                and all(m.get("started") is not None for m in known) else None,
            "structured_test_runs": len(counts), "test_count_coverage": len(counts) / len(metrics) if metrics else None,
            "test_pass_rate_micro": sum(c["passed"] for c in counts) / total if total else None,
            "all_reported_tests_passed_ratio": sum(sum(c.values()) > 0 and c["failed"] == c["errors"] == c["skipped"] == 0
                for c in counts) / len(counts) if counts else None,
            "test_ratio_note": "仅说明报告中的测试，未证明必需测试未漏跑或需求验收完成"}
