"""Gateway v1: frozen DashScope text policy, not a general HTTP proxy."""
import json
from typing import Literal
from pydantic import Field, model_validator
from .platform_run import ProtocolModel


class ModelPolicy(ProtocolModel):
    provider: Literal['dashscope'] = 'dashscope'
    model: str = Field(min_length=1, max_length=100, pattern=r'^qwen[a-zA-Z0-9._-]*$')
    temperature: float = Field(default=0.0, ge=0, lt=2, strict=True)
    max_output_tokens: int = Field(default=2048, ge=1, le=8192, strict=True)
    max_calls: int = Field(default=4, ge=1, le=20, strict=True)
    max_request_bytes: int = Field(default=65536, ge=1024, le=262144, strict=True)
    max_messages: int = Field(default=16, ge=1, le=64, strict=True)
    request_timeout_seconds: int = Field(default=60, ge=1, le=120, strict=True)
    max_total_tokens: int | None = Field(default=None, ge=1, le=1000000, strict=True)
    token_enforcement: Literal['advisory'] = 'advisory'


class TextMessage(ProtocolModel):
    role: Literal['system', 'user', 'assistant']
    content: str = Field(min_length=1, max_length=262144)


class ModelCallRequest(ProtocolModel):
    # Caller may choose only the idempotency key and text, never model/URL/headers.
    call_id: str = Field(min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    messages: list[TextMessage] = Field(min_length=1, max_length=64)


class ModelUsage(ProtocolModel):
    prompt_tokens: int = Field(ge=0, strict=True)
    completion_tokens: int = Field(ge=0, strict=True)
    total_tokens: int = Field(ge=0, strict=True)

    @model_validator(mode='after')
    def coherent(self):
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError('Inconsistent provider usage')
        return self


def forwarded_body(policy: ModelPolicy, call: ModelCallRequest) -> dict:
    """The same canonical bytes must later be sent and hashed by the gateway."""
    if len(call.messages) > policy.max_messages:
        raise ValueError('model_message_limit')
    body = dict(model=policy.model, stream=False, enable_thinking=False,
                temperature=policy.temperature, max_tokens=policy.max_output_tokens,
                messages=[m.model_dump(mode='json') for m in call.messages])
    if len(body_bytes(body)) > policy.max_request_bytes:
        raise ValueError('model_request_byte_limit')
    return body


def body_bytes(body: dict) -> bytes:
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
