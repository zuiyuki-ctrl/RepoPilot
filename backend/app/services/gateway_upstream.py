"""Fixed DashScope protocol; fake default, trusted TLS subclass for explicit live deployment.

Injected adapters are test infrastructure, never Agent-controlled configuration.
"""
import asyncio
from datetime import datetime, timezone

import httpx
from pydantic import ValidationError

from ..schemas.model_gateway import ModelCallRequest, ModelPolicy, ModelUsage, body_bytes, forwarded_body
from .platform_artifacts import decode_json

ENDPOINT = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
MODELS = frozenset({'qwen-plus'})
MAX_RESPONSE_BYTES = 262144


class UpstreamFailure(Exception):
    """Only controlled metadata; never retain a response body, key or HTTP error."""
    def __init__(self, code, *, usage=None):
        super().__init__(code)
        self.code, self.usage = code, usage


def _normalise(data):
    value = decode_json(data)
    if not isinstance(value, dict):
        raise UpstreamFailure('invalid_upstream_response')
    raw_usage, usage, usage_error = value.get('usage'), None, None
    if raw_usage is not None:
        try:
            # Providers may add detailed counters; the ledger uses only these three.
            usage = ModelUsage.model_validate({key: raw_usage[key] for key in
                ('prompt_tokens', 'completion_tokens', 'total_tokens')}).model_dump()
            if usage['total_tokens'] > 1000000:
                raise ValueError('Usage exceeds supported protocol bounds')
        except (ValidationError, KeyError, TypeError, ValueError):
            usage = None
            usage_error = 'invalid_upstream_usage'
    try:
        choices = value['choices']
        if not isinstance(choices, list) or len(choices) != 1 or value.get('error'):
            raise ValueError()
        choice = choices[0]
        message, reason = choice['message'], choice['finish_reason']
        if (choice.get('index') != 0 or isinstance(choice.get('index'), bool)
                or reason not in ('stop', 'length') or message.get('role') != 'assistant'
                or message.get('tool_calls') or message.get('function_call') or message.get('refusal')
                or message.get('reasoning_content')
                or not isinstance(message.get('content'), str) or not message['content'].strip()
                or len(message['content'].encode('utf-8')) > 131072):
            raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        # Valid billing evidence must survive an unusable answer.
        raise UpstreamFailure('invalid_upstream_response', usage=usage) from None
    return dict(message={'role': 'assistant', 'content': message['content']}, usage=usage,
                error_code=usage_error, finish_reason=reason, truncated=reason == 'length',
                usage_source='fake_upstream')


class DashScopeProtocolTransport:
    """Synchronous exchange boundary with cancellable, bounded async HTTP inside.

This base class uses a fixed dummy key. Live TLS overrides only credential/source.
"""
    mode = 'dashscope_fake'
    usage_source = 'fake_upstream'

    def authorization(self):
        return 'Bearer repopilot-fake-upstream-only'

    def __init__(self, *, adapter: httpx.AsyncBaseTransport):
        if not isinstance(adapter, httpx.AsyncBaseTransport):
            raise ValueError('A trusted fake async adapter is required')
        self._adapter = adapter

    def validate(self, body):
        if body.get('model') not in MODELS:
            raise ValueError('Unsupported fixed upstream model')
        # Reconstruct with existing contracts: no arbitrary fields/URLs/headers,
        # stream/thinking/tools, and no silent changes to the frozen request bytes.
        expected = forwarded_body(ModelPolicy(model=body['model'], temperature=body['temperature'],
            max_output_tokens=body['max_tokens'], max_messages=64, max_request_bytes=262144),
            ModelCallRequest(call_id='validate', messages=body['messages']))
        if body != expected or body.get('stream') is not False or body.get('enable_thinking') is not False:
            raise ValueError('Unsupported fixed upstream request')

    def invoke(self, body, *, deadline):
        value = decode_json(body)
        self.validate(value)
        if body_bytes(value) != body:
            raise ValueError('Upstream request must use canonical bytes')
        try:
            return asyncio.run(self._invoke(body, deadline))
        except UpstreamFailure:
            raise
        except (TimeoutError, httpx.TimeoutException):
            raise UpstreamFailure('upstream_timeout') from None
        except (ValueError, UnicodeError, RecursionError):
            raise UpstreamFailure('invalid_upstream_response') from None
        except Exception:
            raise UpstreamFailure('upstream_disconnected') from None

    async def _invoke(self, body, deadline):
        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise UpstreamFailure('upstream_timeout')
        # HTTPX timeouts are phase/inactivity limits, not a total deadline. The
        # outer monotonic timeout also cancels a peer that dribbles bytes forever.
        async with asyncio.timeout(remaining):
            async with httpx.AsyncClient(transport=self._adapter, trust_env=False,
                    follow_redirects=False, timeout=httpx.Timeout(remaining)) as client:
                async with client.stream('POST', ENDPOINT, content=body, headers={
                    'Authorization': self.authorization(),
                    'Content-Type': 'application/json', 'Accept': 'application/json',
                    'Accept-Encoding': 'identity',
                }) as response:
                    # No automatic retries, redirects, fallback models or error-body logging.
                    if response.status_code != 200:
                        raise UpstreamFailure('upstream_rejected')
                    for name in ('content-type', 'content-length', 'content-encoding'):
                        if len(response.headers.get_list(name)) > 1:
                            raise UpstreamFailure('invalid_upstream_response')
                    if (response.headers.get('content-type', '').split(';')[0].strip().lower()
                            != 'application/json'
                            or response.headers.get('content-encoding', 'identity').lower() != 'identity'):
                        raise UpstreamFailure('invalid_upstream_response')
                    declared = response.headers.get('content-length')
                    if declared is not None and (not declared.isascii() or not declared.isdecimal()
                            or len(declared) > 9 or int(declared) > MAX_RESPONSE_BYTES):
                        raise UpstreamFailure('invalid_upstream_response')
                    data = bytearray()
                    # Raw bytes, not decompressed content: compressed responses are rejected.
                    async for chunk in response.aiter_raw():
                        if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise UpstreamFailure('invalid_upstream_response')
                        data.extend(chunk)
                    if declared is not None and len(data) != int(declared):
                        raise UpstreamFailure('invalid_upstream_response')
                    result = _normalise(bytes(data))
                    result['usage_source'] = self.usage_source
                    return result
