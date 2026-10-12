"""只从已保存的事件关联调用观测；不计价、不用当前配置回填历史。"""
from copy import deepcopy


def collect_request_observations(events) -> list[dict]:
    calls = {}
    for event in events:
        if not event.event_type.startswith(("MODEL_CALL_", "EMBEDDING_CALL_")):
            continue
        call_id = event.payload.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            continue
        kind = "embedding" if event.event_type.startswith("EMBEDDING") else "chat"
        key = (kind, event.node_name, call_id)
        row = calls.setdefault(key, {"call_id": call_id, "kind": kind, "phase": event.node_name,
            "scope": event.payload.get("scope", "task"), "started_sequences": [],
            "finished_sequences": [], "observation": None, "completeness": "missing_terminal"})
        if event.event_type.endswith("STARTED"):
            row["started_sequences"].append(event.sequence)
        else:
            row["finished_sequences"].append(event.sequence)
            observation = event.payload.get("model_observation")
            if isinstance(observation, dict) and observation.get("call_id") == call_id:
                row["observation"] = deepcopy(observation)
    for row in calls.values():
        starts, ends = row["started_sequences"], row["finished_sequences"]
        if len(starts) != 1 or len(ends) > 1 or (ends and ends[0] <= starts[0]):
            row["completeness"] = "ambiguous"
            row["observation"] = None
        elif ends:
            row["completeness"] = "recorded" if row["observation"] is not None else "legacy_or_missing"
    return list(calls.values())
