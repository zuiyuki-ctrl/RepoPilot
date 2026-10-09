"""从历史事件构造检索证据报告；不读取工作区、数据库或调用模型。"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from uuid import UUID

from ..schemas.task_event import TaskEventRead


TRACE_EVENTS = {"RETRIEVAL_COMPLETED", "TOOL_CONTEXT_PREPARED"}
MODEL_EVENTS = {"MODEL_CALL_STARTED", "MODEL_CALL_COMPLETED", "MODEL_CALL_FAILED"}
TOOL_EVENTS = {"TOOL_CALL_STARTED", "TOOL_CALL_COMPLETED", "TOOL_CALL_FAILED", "BUDGET_EXCEEDED"}


def _context_key(payload: dict) -> tuple | None:
    index = payload.get("tool_message_index")
    chars = payload.get("content_chars")
    call_id = payload.get("tool_call_id")
    digest = payload.get("content_sha256")
    if (type(index) is not int or index < 0 or type(chars) is not int or chars < 0
            or not isinstance(call_id, str) or not call_id
            or not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)):
        return None
    return index, call_id, digest, chars


def build_retrieval_report(task_id: UUID, events: list[TaskEventRead]) -> dict:
    """保持事件顺序，用工具 call_id 和精确消息指纹连接模型调用，不猜测缺失证据。"""
    previous = 0
    warnings = []
    calls = {}
    models = []
    terminal = {}
    raw_events = []
    model_keys = set()

    for event in events:
        if event.task_id != task_id or event.sequence <= previous:
            raise ValueError("Events must belong to the task and have strictly increasing sequences")
        if "sequence" in event.payload and event.payload["sequence"] != event.sequence:
            raise ValueError("Event payload sequence differs from event sequence")
        if event.sequence != previous + 1:
            warnings.append(f"事件序号 {previous} 到 {event.sequence} 之间存在缺口")
        previous = event.sequence
        if event.event_type not in TRACE_EVENTS | MODEL_EVENTS | TOOL_EVENTS:
            continue
        raw_events.append(event.model_dump(mode="json"))
        payload = deepcopy(event.payload)
        call_id = payload.get("call_id")

        if event.event_type in MODEL_EVENTS:
            if not isinstance(call_id, str) or not call_id:
                warnings.append(f"事件 {event.sequence} 缺少模型 call_id，未关联")
                continue
            key = (event.node_name, call_id)
            if event.event_type == "MODEL_CALL_STARTED":
                if key in model_keys:
                    raise ValueError("Duplicate model call_id in the same node")
                model_keys.add(key)
                models.append({"call_id": call_id, "node_name": event.node_name,
                    "started_sequence": event.sequence, "payload": payload})
            else:
                terminal.setdefault(key, []).append(event)
            continue

        if not isinstance(call_id, str) or not call_id:
            # 整批拒绝没有单次工具 ID，原事件保留，但不编造工具调用。
            continue
        row = calls.setdefault(call_id, {
            "call_id": call_id, "tool_call_id": payload.get("tool_call_id"),
            "tool_name": payload.get("tool_name"), "event_sequences": [],
            "retrieval": None, "context": None, "model_calls": [],
        })
        row["event_sequences"].append(event.sequence)
        if any(payload.get(field) != row[field] for field in ("tool_call_id", "tool_name")):
            raise ValueError("Tool identity differs across events with the same call_id")
        if event.event_type not in TRACE_EVENTS:
            continue
        if payload.get("trace_version") != 1:
            warnings.append(f"事件 {event.sequence} 的 trace_version 不支持，保留原始事件")
            continue
        field = "retrieval" if event.event_type == "RETRIEVAL_COMPLETED" else "context"
        if row[field] is not None:
            raise ValueError(f"Duplicate {field} evidence for call_id={call_id}")
        row[field] = {"sequence": event.sequence, "payload": payload}

    for model in models:
        ends = [event for event in terminal.get((model["node_name"], model["call_id"]), [])
                if event.sequence > model["started_sequence"]]
        model["outcome"] = ("unrecorded" if not ends else
                            "ambiguous" if len(ends) != 1 else
                            "completed" if ends[0].event_type == "MODEL_CALL_COMPLETED" else "failed")
        model["finished_sequence"] = ends[0].sequence if len(ends) == 1 else None
        model["unmatched_tool_context"] = []
        payload = model["payload"]
        references = payload.get("tool_context")
        if payload.get("trace_version") != 1 or not isinstance(references, list):
            model["context_recorded"] = False
            continue
        model["context_recorded"] = True
        for ref in references:
            key = _context_key(ref) if isinstance(ref, dict) else None
            matches = [row for row in calls.values() if key is not None and row["context"]
                       and row["context"]["sequence"] < model["started_sequence"]
                       and _context_key(row["context"]["payload"]) == key]
            if len(matches) != 1:
                model["unmatched_tool_context"].append(deepcopy(ref))
                warnings.append(f"模型事件 {model['started_sequence']} 的工具消息无法唯一关联，未猜测来源")
                continue
            matches[0]["model_calls"].append({
                "call_id": model["call_id"], "node_name": model["node_name"],
                "started_sequence": model["started_sequence"],
                "finished_sequence": model["finished_sequence"], "outcome": model["outcome"],
            })

    rows = list(calls.values())
    has_trace = any(row["retrieval"] or row["context"] for row in rows) or any(m["context_recorded"] for m in models)
    incomplete = bool(warnings) or any(row["context"] is None for row in rows)
    for row in rows:
        if (row["tool_name"] == "search_code" and row["context"]
                and row["context"]["payload"].get("disposition") == "accepted" and not row["retrieval"]):
            incomplete = True
    return {
        "schema_version": 1, "task_id": str(task_id),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_scope": "events_observed_until_empty_page",
        "last_sequence": previous, "event_count": len(events),
        "trace_status": "not_recorded" if not has_trace else "partial" if incomplete else "recorded",
        "warnings": warnings, "tool_calls": rows, "model_calls": models,
        "events": raw_events,
    }


def _literal(lines: list[str], value) -> None:
    """自由文本缩进展示，不让查询、路径或符号内容改变 Markdown 结构。"""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    lines.append("")
    lines.extend("    " + line for line in text.splitlines() or ["（空）"])
    lines.append("")


def render_retrieval_report(report: dict) -> str:
    labels = {"not_recorded": "未记录", "partial": "部分记录", "recorded": "已记录"}
    lines = ["# 检索与工具上下文证据", "", f"- 任务 ID：{report['task_id']}",
             f"- 证据状态：{labels[report['trace_status']]}",
             f"- 读取事件数：{report['event_count']}；末尾序号：{report['last_sequence']}", "",
             "这是读取时可见事件的快照；运行中的任务可能继续追加事件。",
             "模型调用成功不等于模型语义上采纳了证据；hash 不能独自重建源码。", ""]
    if report.get("experiment") is not None:
        lines.append("实验关联：")
        _literal(lines, report["experiment"])
    if report.get("task_snapshot_before_event_fetch") is not None:
        lines.append("读取事件前的任务状态与配置快照：")
        _literal(lines, report["task_snapshot_before_event_fetch"])
    if report["trace_status"] == "not_recorded":
        lines.append("未记录新版检索 / 上下文证据，不从当前索引或工作区补造历史。")
    for number, row in enumerate(report["tool_calls"], start=1):
        lines.extend(["", f"## 工具调用 {number}", ""])
        _literal(lines, {k: row[k] for k in ("call_id", "tool_call_id", "tool_name", "event_sequences")})
        retrieval = row["retrieval"]
        if retrieval is None:
            lines.append("检索结果摘要：未记录（源码读取、跳过或失败也可能没有检索事件）。")
        else:
            payload = retrieval["payload"]
            lines.append(f"检索事件序号：{retrieval['sequence']}；结果范围为工具返回 Top-K。")
            _literal(lines, {k: payload.get(k) for k in ("query", "effective_query", "requested_strategy",
                "retrieval_strategy", "top_k", "retrieval_parameters", "diagnostics")})
            hits = payload.get("hits", [])
            lines.append(f"返回 {len(hits)} 条命中，以下保持原顺序：")
            for hit in hits:
                _literal(lines, hit)
        context = row["context"]
        if context is None:
            lines.append("预算后工具消息：未记录，不能推断为已发送。")
        else:
            lines.append(f"预算后消息事件序号：{context['sequence']}")
            _literal(lines, context["payload"])
        if not row["model_calls"]:
            lines.append("没有唯一匹配的后续模型调用记录，不能推断已提交。")
        else:
            lines.append("关联的后续模型调用尝试（completed / failed / unrecorded）：")
            _literal(lines, row["model_calls"])
    lines.extend(["", "## 模型调用清单", ""])
    for model in report["model_calls"]:
        _literal(lines, {k: model[k] for k in ("call_id", "node_name", "started_sequence",
            "finished_sequence", "outcome", "context_recorded", "unmatched_tool_context")})
    if report["warnings"]:
        lines.extend(["", "## 关联缺口", ""])
        _literal(lines, report["warnings"])
    return "\n".join(lines) + "\n"
