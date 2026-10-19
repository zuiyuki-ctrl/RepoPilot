"""B3 fake protocol + actual localhost HTTP; no provider key, DB or paid request."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import time
from types import SimpleNamespace as NS

import httpx
import pytest

from backend.app.schemas.model_gateway import body_bytes, forwarded_body, ModelCallRequest
from backend.app.services import gateway_credentials as credentials, model_gateway_service as ledger_service
from backend.app.services.gateway_exchange import GatewayExchange, GatewayUpstreamUnknown
from backend.app.services.gateway_upstream import DashScopeProtocolTransport, UpstreamFailure, ENDPOINT
from backend.app.services.run_lifecycle import RunConflictError
from tests.test_model_gateway import ledger, payload, USAGE


def answer(**changes):
    return {'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'fake answer'},
                         'finish_reason': 'stop'}], 'usage': dict(USAGE), **changes}


def response(value=None, *, status=200, headers=None, raw=None):
    return httpx.Response(status, headers={'Content-Type': 'application/json', **(headers or {})},
                          stream=httpx.ByteStream(raw if raw is not None else body_bytes(value or answer())))


@pytest.fixture
def fake_gateway(ledger, monkeypatch, tmp_path):
    l = ledger
    l.grant.gateway_mode = 'dashscope_fake'  # Trusted test setup, not a credential issuer bypass in production.
    monkeypatch.setattr('backend.app.services.platform_artifacts.run_directory', lambda run_id: tmp_path)
    identity = NS(run_id=l.run.id, worker_token=l.token, policy=l.config.model_policy, mode='dashscope_fake')
    return NS(l=l, identity=identity, root=tmp_path)


def exchange(g, handler):
    return GatewayExchange(transport=DashScopeProtocolTransport(adapter=httpx.MockTransport(handler)))


def test_exact_frozen_request_usage_and_cached_reply(fake_gateway, monkeypatch):
    g = fake_gateway
    calls = []
    monkeypatch.setenv('HTTPS_PROXY', 'http://unreachable.invalid:1')
    monkeypatch.setenv('SSL_CERT_FILE', '/nonexistent-provider-ca')
    def handler(request):
        calls.append(request)
        assert str(request.url) == ENDPOINT and request.method == 'POST'
        assert request.headers['Authorization'] == 'Bearer repopilot-fake-upstream-only'
        assert request.headers['Accept-Encoding'] == 'identity'
        return response(answer(usage={**USAGE, 'prompt_tokens_details': {'cached_tokens': 0}}))
    service = exchange(g, handler)
    first = service.call(g.identity, payload())
    assert first == service.call(g.identity, payload())
    assert first['usage'] == USAGE and first['usage_source'] == 'fake_upstream'
    assert first['transport'] == 'dashscope_fake' and not first['truncated']
    assert len(calls) == g.l.grant.calls_reserved == 1
    assert hashlib.sha256(calls[0].content).hexdigest() == first['request_sha256']
    assert json.loads(calls[0].content)['enable_thinking'] is False
    service.call(g.identity, payload(call_id='second'))
    assert len(calls) == 2 and g.l.grant.known_total_tokens == 30
    with pytest.raises(RunConflictError): service.call(g.identity, payload(call_id='third'))
    saved = ''.join(p.read_text(encoding='utf-8') for p in g.root.rglob('*.json'))
    assert 'Bearer' not in saved and 'repopilot-fake-upstream-only' not in saved


@pytest.mark.parametrize('usage', [None, {}, {'total_tokens': 3},
    {**USAGE, 'total_tokens': 99}, {**USAGE, 'prompt_tokens': True},
    {'prompt_tokens': 1000001, 'completion_tokens': 0, 'total_tokens': 1000001}])
def test_missing_or_bad_usage_keeps_answer_but_closes_budget(fake_gateway, usage):
    g = fake_gateway
    service = exchange(g, lambda r: response(answer(usage=usage)))
    result = service.call(g.identity, payload())
    assert result['status'] == 'succeeded' and result['usage'] is None
    assert result['error_code'] == (None if usage is None else 'invalid_upstream_usage')
    assert g.l.grant.known_total_tokens == 0 and g.l.grant.stop_reason == 'usage_missing'
    assert service.call(g.identity, payload()) == result
    with pytest.raises(RunConflictError): service.call(g.identity, payload(call_id='next'))


def test_length_is_not_silently_reported_as_complete(fake_gateway):
    value = answer(); value['choices'][0]['finish_reason'] = 'length'
    service = exchange(fake_gateway, lambda r: response(value))
    result = service.call(fake_gateway.identity, payload())
    assert result['truncated'] is True and result['finish_reason'] == 'length'
    assert result['usage'] == USAGE


@pytest.mark.parametrize('status', [301, 307, 400, 401, 429, 500, 503])
def test_http_errors_never_follow_redirects_or_retry(fake_gateway, status):
    calls = []
    def handler(request):
        calls.append(request)
        return response(status=status, headers={'Location': 'http://unreachable.invalid/private'},
                        raw=b'secret provider error must not be saved')
    service = exchange(fake_gateway, handler)
    with pytest.raises(GatewayUpstreamUnknown): service.call(fake_gateway.identity, payload())
    result = service.call(fake_gateway.identity, payload())
    assert result['status'] == 'unknown' and result['error_code'] == 'upstream_rejected'
    assert len(calls) == fake_gateway.l.grant.calls_reserved == 1
    assert not (fake_gateway.root / 'gateway' / 'responses').exists()


@pytest.mark.parametrize('kind', ['empty', 'tools', 'refusal', 'thinking', 'multiple', 'filtered'])
def test_unusable_answer_still_preserves_known_usage(fake_gateway, kind):
    value = answer(); choice = value['choices'][0]
    if kind == 'empty': choice['message']['content'] = ''
    elif kind == 'tools': choice['message']['tool_calls'] = [{'id': 'not-supported'}]
    elif kind == 'refusal': choice['message']['refusal'] = 'refused'
    elif kind == 'thinking': choice['message']['reasoning_content'] = 'unexpected'
    elif kind == 'multiple': value['choices'] *= 2
    else: choice['finish_reason'] = 'content_filter'
    service = exchange(fake_gateway, lambda r: response(value))
    with pytest.raises(GatewayUpstreamUnknown): service.call(fake_gateway.identity, payload())
    result = service.call(fake_gateway.identity, payload())
    assert result['error_code'] == 'invalid_upstream_response' and result['usage'] == USAGE
    assert fake_gateway.l.grant.known_total_tokens == 15


@pytest.mark.parametrize('headers,raw', [({}, b'{bad'), ({}, b'{"choices":[],"choices":[]}'),
    ({}, b'x' * 262145), ({'Content-Length': '262145'}, b''), ({'Content-Length': '2'}, b'{} '),
    ({'Content-Encoding': 'gzip'}, b'compressed'), ({'Content-Type': 'text/html'}, b'<html>')],
    ids=['invalid-json', 'duplicate-key', 'oversized', 'oversized-declared', 'length-mismatch', 'compressed', 'html'])
def test_bounded_response_validation(fake_gateway, headers, raw):
    service = exchange(fake_gateway, lambda r: response(headers=headers, raw=raw))
    with pytest.raises(GatewayUpstreamUnknown): service.call(fake_gateway.identity, payload())
    assert fake_gateway.l.calls[0].error_code == 'invalid_upstream_response'


def test_response_artifact_failure_keeps_billing_evidence(fake_gateway, monkeypatch):
    service = exchange(fake_gateway, lambda r: response())
    original = service.artifacts.write
    def fail(run_id, kind, value):
        if kind == 'responses': raise OSError('private path')
        return original(run_id, kind, value)
    monkeypatch.setattr(service.artifacts, 'write', fail)
    with pytest.raises(GatewayUpstreamUnknown): service.call(fake_gateway.identity, payload())
    assert fake_gateway.l.calls[0].usage == USAGE and fake_gateway.l.grant.known_total_tokens == 15


def test_cancel_during_upstream_preserves_late_evidence(fake_gateway):
    g = fake_gateway
    def handler(request):
        ledger_service.revoke_attempt(g.l.session, g.l.run)
        g.l.work.cancel_requested = True
        return response()
    service = exchange(g, handler)
    with pytest.raises(credentials.GatewayUnauthorized): service.call(g.identity, payload())
    assert g.l.calls[0].status == 'succeeded' and g.l.grant.known_total_tokens == 15


def test_unapproved_model_rejected_before_reservation(fake_gateway):
    g = fake_gateway
    g.identity.policy = g.identity.policy.model_copy(update={'model': 'qwen-not-approved'})
    service = exchange(g, lambda r: pytest.fail('must not dispatch'))
    with pytest.raises(ValueError): service.call(g.identity, payload())
    assert not g.l.calls and g.l.grant.calls_reserved == 0


def test_live_and_fake_modes_cannot_be_issued(ledger):
    for mode in ('dashscope', 'dashscope_fake'):
        with pytest.raises(ValueError): credentials.issue_credential(ledger.run.id, ledger.token, mode=mode)
    with pytest.raises(TypeError): DashScopeProtocolTransport()
    with pytest.raises(ValueError): GatewayExchange(transport=NS(mode='dashscope'))


@pytest.mark.parametrize('failure,code', [(httpx.ReadTimeout, 'upstream_timeout'),
                                        (httpx.ConnectError, 'upstream_disconnected')])
def test_network_errors_are_redacted_and_not_retried(fake_gateway, failure, code):
    calls = []
    async def handler(request):
        calls.append(request)
        raise failure('private provider details')
    service = exchange(fake_gateway, handler)
    with pytest.raises(GatewayUpstreamUnknown) as error:
        service.call(fake_gateway.identity, payload())
    result = service.call(fake_gateway.identity, payload())
    assert result['error_code'] == code and len(calls) == 1
    assert 'private' not in str(error.value) and fake_gateway.l.grant.calls_reserved == 1


def test_actual_local_http_dribble_cancelled_by_total_deadline(fake_gateway):
    async def exercise():
        received, finished = [], asyncio.Event()
        async def handler(reader, writer):
            try:
                header = await reader.readuntil(b'\r\n\r\n')
                size = int(next(line.split(b':', 1)[1] for line in header.split(b'\r\n')
                                if line.lower().startswith(b'content-length:')))
                received.append(await reader.readexactly(size))
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                             b'Transfer-Encoding: chunked\r\n\r\n')
                # Bytes keep arriving faster than the inactivity timeout.
                for _ in range(100):
                    writer.write(b'1\r\n \r\n'); await writer.drain(); await asyncio.sleep(0.02)
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            finally:
                writer.close()
                try: await writer.wait_closed()
                except ConnectionError: pass
                finished.set()
        server = await asyncio.start_server(handler, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        class LocalOnly(httpx.AsyncBaseTransport):
            def __init__(self): self.inner = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
            async def handle_async_request(self, request):
                assert str(request.url) == ENDPOINT
                request.url = httpx.URL(f'http://127.0.0.1:{port}/fixture')
                return await self.inner.handle_async_request(request)
            async def aclose(self): await self.inner.aclose()
        async with server:
            transport = DashScopeProtocolTransport(adapter=LocalOnly())
            body = body_bytes(forwarded_body(fake_gateway.identity.policy, ModelCallRequest(**payload())))
            start = time.monotonic()
            with pytest.raises(UpstreamFailure) as error:
                await asyncio.to_thread(transport.invoke, body,
                    deadline=datetime.now(timezone.utc) + timedelta(seconds=0.3))
            assert error.value.code == 'upstream_timeout'
            assert time.monotonic() - start < 1.5
            await asyncio.wait_for(finished.wait(), 2)
            assert received == [body]
    asyncio.run(exercise())
