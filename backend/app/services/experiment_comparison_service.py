"""离线实验对照：仅处理传入的历史数据，不访问数据库、工作区或模型。"""
from datetime import datetime, timezone
import json

from pydantic import TypeAdapter

from ..schemas.experiment import ExperimentPreparation
from ..schemas.task_report import TaskExecutionReport
from ..schemas.task_event import TaskEventRead
from .retrieval_report_service import build_retrieval_report


def summarize_run(preparation: dict, report: dict | None, evidence: dict | None) -> dict:
    """核对三个 artifact 的身份，再提取本次终态与规划阶段观测。"""
    prep = ExperimentPreparation.model_validate(preparation)
    strategy = prep.run_config.retrieval_policy
    if strategy not in ("vector", "hybrid"):
        raise ValueError("Comparison requires a fixed vector/hybrid policy")
    row = {
        "experiment_id": str(prep.experiment_id), "case": prep.case.model_dump(mode="json"),
        "strategy": strategy, "run_config": prep.run_config.model_dump(mode="json"),
        "task_id": str(prep.task_id) if prep.task_id else None,
        "preparation_status": prep.status, "preparation_stage": prep.stage,
        "preparation_error_type": prep.error_type,
        "protected_test_file_hashes": prep.protected_test_file_hashes,
        "status": "report_missing", "test": None, "retry_count": None,
        "completion_event_sequence": None, "failure": None, "final_diff": None,
        "retrieval": None, "token_usage": None, "cost": None,
    }
    if report is None:
        if evidence is not None:
            raise ValueError("Evidence without a task report is not supported in this comparison")
        if prep.status == "error":
            row["status"] = "preparation_error"
        elif prep.status == "preparing":
            row["status"] = "preparation_incomplete"
        return row

    task_report = TaskExecutionReport.model_validate(report)
    task = task_report.task
    if (prep.status != "prepared" or task.id != prep.task_id
            or task.repository_id != prep.repository_id or task.run_config != prep.run_config
            or task.user_request != prep.case.user_request.strip() or task.task_type != "plan"):
        raise ValueError("Task report differs from preparation")
    if task.status not in ("completed", "failed"):
        raise ValueError("Expected a terminal historical report")
    if task.result is not None and task.result.repository_id != prep.repository_id:
        raise ValueError("Task result belongs to another repository")
    run = task_report.test_run
    if run is not None and run.task_id != task.id:
        raise ValueError("TestRun belongs to another task")
    passed = (run is not None and run.status == "finished" and run.exit_code == 0
              and not run.timed_out and run.error is None)
    diff = task_report.final_diff
    if diff is not None:
        if diff.task_id != task.id or diff.repository_id != task.repository_id:
            raise ValueError("Diff belongs to another task/repository")
        changed = set(diff.changed_files) | set(diff.untracked_files)
        if not changed <= set(prep.case.editable_files):
            raise ValueError("Historical diff is outside the declared editable scope")
    if task.status == "completed" and (
        not passed or task_report.completion_event_sequence is None
        or task_report.failure is not None or task.error is not None
        or task.review_decision != "approved" or task.reviewed_at is None
        or task.result is None or run.snapshot_hash is None
    ):
        raise ValueError("Completed report lacks consistent approval/test/completion evidence")
    if task.status == "failed" and task_report.failure is None:
        raise ValueError("Failed report lacks failure evidence")
    row.update(status=task.status, retry_count=task.retry_count,
               max_retries=task.max_retries,
               completion_event_sequence=task_report.completion_event_sequence,
               failure=task_report.failure.model_dump(mode="json") if task_report.failure else None,
               final_diff=diff.model_dump(mode="json") if diff else None,
               review={"decision": task.review_decision, "comment": task.review_comment,
                       "reviewed_at": task.reviewed_at.isoformat() if task.reviewed_at else None})
    if run is not None:
        # 保留 stdout 原文，不将非结构化 pytest 文本当作可靠的计数协议。
        row["test"] = {**run.model_dump(mode="json"), "process_passed": passed,
                       "structured_test_counts": None}
    if evidence is None:
        return row
    expected_experiment = {
        "experiment_id": str(prep.experiment_id), "case_id": prep.case.case_id,
        "case_version": prep.case.case_version, "repository_commit": prep.case.repository_commit,
    }
    snapshot = evidence.get("task_snapshot_before_event_fetch", {})
    if (evidence.get("schema_version") != 1 or evidence.get("task_id") != str(task.id)
            or evidence.get("experiment") != expected_experiment
            or snapshot.get("id") != str(task.id)
            or snapshot.get("repository_id") != str(task.repository_id)
            or snapshot.get("run_config") != row["run_config"]):
        raise ValueError("Retrieval evidence differs from experiment/task/config")
    events = TypeAdapter(list[TaskEventRead]).validate_python(evidence.get("events"))
    event_count, last_sequence = evidence.get("event_count"), evidence.get("last_sequence")
    if (type(event_count) is not int or event_count < len(events)
            or type(last_sequence) is not int or last_sequence < 0
            or any(event.sequence > last_sequence for event in events)):
        raise ValueError("Invalid evidence snapshot counters")
    # 导出只保留相关事件，序号有间隔是合法的；重新关联，避免信任可编辑的摘要。
    rebuilt = build_retrieval_report(task.id, events)
    # 原导出只保存相关事件，重放时的序号间隔不能推断为原采集缺口。
    # 完整性状态沿用原快照；工具/模型关联则重新计算，并单独保留关联告警。
    if evidence.get("trace_status") not in ("recorded", "partial", "not_recorded"):
        raise ValueError("Unknown exported trace status")
    association_warnings = [warning for warning in rebuilt["warnings"]
                            if not warning.startswith("事件序号 ")]
    queries = []
    contexts = []
    for call in rebuilt["tool_calls"]:
        retrieval = call["retrieval"]
        if retrieval is not None:
            payload = retrieval["payload"]
            if (payload.get("repository_id") != str(task.repository_id)
                    or payload.get("retrieval_strategy") != strategy):
                raise ValueError("Actual retrieval strategy/repository differs from preparation")
            queries.append({"event_sequence": retrieval["sequence"],
                            **{key: payload.get(key) for key in (
                                "query", "requested_strategy", "retrieval_strategy", "top_k",
                                "diagnostics", "retrieval_parameters", "hits")}})
        if call["context"] is not None:
            context = call["context"]["payload"]
            contexts.append({"tool_name": call["tool_name"],
                "event_sequence": call["context"]["sequence"],
                "disposition": context["disposition"], "content_chars": context["content_chars"],
                "model_calls": call["model_calls"]})
    row["retrieval"] = {
        "trace_status": evidence["trace_status"],
        "trace_status_source": "original_export_snapshot",
        "association_warnings": association_warnings,
        "exported_event_count": evidence.get("event_count"),
        "snapshot_last_sequence": evidence.get("last_sequence"),
        "scope": "exported_retrieval_context_events_only",
        "warnings": evidence.get("warnings", []), "queries": queries, "contexts": contexts,
        "model_calls": [{"node_name": call["node_name"], "outcome": call["outcome"],
            "model": call["payload"].get("model"),
            "system_prompt_sha256": call["payload"].get("system_prompt_sha256"),
            "unmatched_tool_context": call["unmatched_tool_context"]}
            for call in rebuilt["model_calls"]],
    }
    return row


def build_comparison(rows: list[dict]) -> dict:
    """显式主运行一例两组，准备失败/中断单列，绝不自动选择最佳运行。"""
    seen_experiments, seen_tasks = set(), set()
    groups, additional = {}, []
    for row in rows:
        if row["experiment_id"] in seen_experiments:
            raise ValueError("Duplicate experiment")
        seen_experiments.add(row["experiment_id"])
        if row["task_id"]:
            if row["task_id"] in seen_tasks:
                raise ValueError("Task reused across experiments")
            seen_tasks.add(row["task_id"])
        if row["role"] == "additional":
            additional.append(row)
            continue
        case = row["case"]
        pair = groups.setdefault((case["case_id"], case["case_version"]), {})
        if row["strategy"] in pair:
            raise ValueError("Multiple primary runs for one case/strategy; select explicitly")
        pair[row["strategy"]] = row
    pairs = []
    for (case_id, version), pair in sorted(groups.items()):
        differences = []
        left, right = pair.get("vector"), pair.get("hybrid")
        if left and right:
            for name in ("case", "protected_test_file_hashes", "max_retries"):
                if left.get(name) != right.get(name):
                    differences.append(name)
            if left["run_config"]["max_tool_calls"] != right["run_config"]["max_tool_calls"]:
                differences.append("max_tool_calls")
            for name in ("image", "timeout_seconds"):
                if (left["test"] or {}).get(name) != (right["test"] or {}).get(name):
                    differences.append(name)
            if left["retrieval"] and right["retrieval"]:
                def models(row):
                    return sorted({call["model"] for call in row["retrieval"]["model_calls"]
                                   if call["model"] is not None})
                if models(left) != models(right):
                    differences.append("observed_models")
        pairs.append({"case_id": case_id, "case_version": version, "runs": pair,
                      "recorded_condition_differences": differences,
                      "pair_complete": left is not None and right is not None})
    counts = {strategy: {status: sum(
        row["role"] == "primary" and row["strategy"] == strategy and row["status"] == status
        for row in rows) for status in ("completed", "failed", "report_missing",
                                      "preparation_error", "preparation_incomplete")}
        for strategy in ("vector", "hybrid")}
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "primary_status_counts": counts,
            "pairs": pairs, "additional_attempts": additional,
            "limitations": [
                "每个配置每例仅一次运行，模型查询可能不同，不能宣称统计显著提升。",
                "completed + 关联测试进程通过不是对全部需求的自动语义证明；人工审批仍参与流程。",
                "未计算通用任务成功率；额外准备失败和未完成记录单列，未知状态不填成功或失败。",
                "规划证据快照不等于完整终态轨迹；not_recorded 或缺文件不等于零次检索。",
                "未采集的结构化测试计数、token 和成本为 null；不从字符数估算，不比较人工等待耗时。",
                "当前可比性只核对已保存用例、测试 hash、预算、镜像标签及超时；镜像 digest、完整生成参数和索引版本不齐，不能认证所有条件一致。",
            ]}


def render_comparison(report: dict) -> str:
    def cell(value):
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(
            "|", "&#124;").replace("\n", " ").replace("\r", " ").replace("`", "&#96;")

    lines = ["# RepoPilot 实验逐例对照", "", "| 用例 | Vector | Hybrid | 条件差异 |",
             "|---|---|---|---|"]
    for pair in report["pairs"]:
        columns = []
        for strategy in ("vector", "hybrid"):
            row = pair["runs"].get(strategy)
            if row is None:
                columns.append("未提供")
            else:
                test = row["test"]
                columns.append(cell(row["status"]) + (f" / exit={test['exit_code']}" if test else " / 无测试记录"))
        lines.append(f"| {cell(pair['case_id'])} / {cell(pair['case_version'])} | "
                     + " | ".join(columns) + " | "
                     + cell(", ".join(pair["recorded_condition_differences"]) or "已记录字段未发现差异；非全面认证") + " |")
    lines.extend(["", "## 口径与限制", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    rows = [row for pair in report["pairs"] for row in pair["runs"].values()]
    rows += report["additional_attempts"]
    for row in rows:
        lines.extend(["", f"## {cell(row['case']['case_id'])} / {cell(row['strategy'])} / {cell(row['role'])}", ""])
        summary = {key: row.get(key) for key in ("experiment_id", "task_id", "status",
                   "preparation_stage", "preparation_error_type", "retry_count", "completion_event_sequence")}
        lines.extend("    " + line for line in json.dumps(summary, ensure_ascii=False, indent=2).splitlines())
        for label, artifact in row["artifacts"].items():
            if artifact:
                lines.extend(["", f"[{cell(label)}]({artifact['uri']})", "",
                              f"    sha256: {artifact['sha256']}"])
        if row["test"]:
            lines.extend(["", "测试输出（原文；不将其解析成结构化计数）：", ""])
            lines.extend("    " + line for line in row["test"]["stdout"].splitlines())
        retrieval = row["retrieval"]
        lines.extend(["", "检索证据：" + (retrieval["trace_status"] if retrieval else "未提供"), ""])
        if retrieval:
            for query in retrieval["queries"]:
                summary = {"query": query["query"], "sequence": query["event_sequence"],
                           "diagnostics": query["diagnostics"],
                           "hits": [{key: hit.get(key) for key in ("rank", "file_path", "symbol_name", "vector_rank", "keyword_rank")}
                                    for hit in query["hits"]]}
                lines.extend("    " + line for line in json.dumps(summary, ensure_ascii=False, indent=2).splitlines())
                lines.append("")
    return "\n".join(lines) + "\n"
