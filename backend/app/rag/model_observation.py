"""每次调用独享的观测对象；不保存请求正文、认证头或异常文本。"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

import httpx


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _label(value):
    return value[:256] if isinstance(value, str) else None


@dataclass
class ModelObservation:
    call_id: str = field(default_factory=lambda: str(uuid4()))
    observation_version: int = 1
    request_kind: str = "chat"
    request_attempted: bool = False
    request_status: str = "not_started"
    failure_stage: str | None = None
    error_type: str | None = None
    requested_model: str | None = None
    response_model: str | None = None
    response_id: str | None = None
    finish_reason: str | None = None
    http_status: int | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    request_parameters: dict = field(default_factory=dict)
    usage: dict = field(default_factory=lambda: {
        "input_tokens": None, "output_tokens": None, "total_tokens": None,
        "cached_input_tokens": None, "reasoning_output_tokens": None,
    })
    usage_status: str = "missing"
    validation_stage: str = "preflight"

    def to_payload(self, error: Exception | None = None) -> dict:
        result = asdict(self)
        result["operation_status"] = "failed" if error is not None else "succeeded"
        if error is not None:
            result["failure_stage"] = self.failure_stage or self.validation_stage
            result["error_type"] = type(error).__name__
        return result

    def capture_response(self, payload):
        if not isinstance(payload, dict):
            return
        self.response_model = _label(payload.get("model"))
        self.response_id = _label(payload.get("id"))
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            self.finish_reason = _label(choices[0].get("finish_reason"))
        raw = payload.get("usage")
        if raw is None:
            return
        if not isinstance(raw, dict):
            self.usage_status = "invalid"
            return
        for target, source in (("input_tokens", "prompt_tokens"),
                               ("output_tokens", "completion_tokens"),
                               ("total_tokens", "total_tokens")):
            self.usage[target] = _count(raw.get(source))
        for target, group, source in (
            ("cached_input_tokens", "prompt_tokens_details", "cached_tokens"),
            ("reasoning_output_tokens", "completion_tokens_details", "reasoning_tokens"),
        ):
            details = raw.get(group)
            if isinstance(details, dict):
                self.usage[target] = _count(details.get(source))
        keys = ("input_tokens", "total_tokens") if self.request_kind == "embedding" else ("input_tokens", "output_tokens", "total_tokens")
        counts = [self.usage[key] for key in keys]
        self.usage_status = "complete" if all(v is not None for v in counts) else "partial"
        if not any(v is not None for v in self.usage.values()):
            self.usage_status = "invalid"
        if self.request_kind == "chat" and all(v is not None for v in counts) and counts[0] + counts[1] != counts[2]:
            self.usage_status = "inconsistent"


def post_chat(client, url, *, headers, body, observation: ModelObservation):
    """不改变 HTTP 异常类型；响应元数据先于 assistant/业务结构校验捕获。"""
    if observation.request_attempted:
        raise ValueError("A model observation cannot be reused for another request")
    observation.requested_model = body["model"]
    observation.request_parameters = {key: body[key] for key in (
        "stream", "enable_thinking", "max_tokens", "temperature", "top_p", "seed", "tool_choice", "dimensions", "encoding_format",
    ) if key in body}
    observation.request_parameters["tools_present"] = bool(body.get("tools"))
    observation.started_at = datetime.now(timezone.utc).isoformat()
    started = perf_counter()
    observation.request_attempted = True
    stage = "transport"
    try:
        response = client.post(url, json=body, headers=headers)
        observation.http_status = response.status_code if type(response.status_code) is int else None
        stage = "http_status"
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            # 错误响应若仍带有用量也保留；错误正文和认证信息不进入观测。
            try:
                observation.capture_response(response.json())
            except ValueError:
                pass
            raise
        stage = "response_json"
        payload = response.json()
        observation.capture_response(payload)
        observation.request_status = "response_received"
        observation.validation_stage = "response_validation"
        return payload
    except (httpx.HTTPError, ValueError) as exc:
        observation.request_status = "failed"
        observation.failure_stage = stage
        observation.error_type = type(exc).__name__
        raise
    finally:
        observation.duration_ms = int((perf_counter() - started) * 1000)
        observation.completed_at = datetime.now(timezone.utc).isoformat()
