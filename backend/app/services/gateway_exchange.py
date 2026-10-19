"""Trusted ledger exchange. Production stays mock-only; fake protocol acceptance is injectable."""
from datetime import datetime, timezone
import hashlib
from ..schemas.model_gateway import ModelCallRequest, body_bytes, forwarded_body
from . import model_gateway_service as ledger, gateway_credentials as credentials
from . import platform_artifacts as artifacts
from .repository_scanner import _is_link_or_reparse_point
from .run_lifecycle import RunConflictError
from .gateway_upstream import UpstreamFailure


class GatewayUpstreamUnknown(Exception):
    pass


class GatewayArtifactUnavailable(Exception):
    pass


class GatewayArtifactStore:
    """Outside Agent input/output mounts; no credentials or headers are accepted."""
    def _directory(self, run_id, kind):
        if kind not in ('requests', 'responses'):
            raise ValueError('Unsupported gateway artifact kind')
        root = artifacts.run_directory(run_id)
        if not root.is_dir():
            raise ValueError('Run artifacts not prepared')
        for name in ('gateway', kind):
            root = root / name
            root.mkdir(exist_ok=True)
            if _is_link_or_reparse_point(root):
                raise ValueError('Unsafe gateway artifact directory')
        return root

    def write(self, run_id, kind, value):
        data = body_bytes(value)
        if len(data) > 300000:
            raise ValueError('Gateway artifact exceeds limit')
        digest = hashlib.sha256(data).hexdigest()
        path = self._directory(run_id, kind) / f'{digest}.json'
        try:
            with path.open('xb') as stream:
                stream.write(data)
        except FileExistsError:
            if artifacts.read_bytes(path, limit=300000) != data:
                raise ValueError('Immutable gateway artifact differs')
        return digest

    def read(self, run_id, digest):
        import re
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid gateway artifact reference')
        data = artifacts.read_bytes(self._directory(run_id, 'responses') / f'{digest}.json', limit=300000)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Gateway artifact hash mismatch')
        return artifacts.decode_json(data)


class DatabaseGatewayStore:
    authenticate = staticmethod(credentials.authenticate)

    def reserve(self, identity, data):
        return ledger.reserve_call(identity.run_id, identity.worker_token, data)

    def dispatch(self, identity, call_id):
        return ledger.mark_dispatched(identity.run_id, identity.worker_token, call_id)

    def finish(self, identity, call_id, **kwargs):
        return ledger.finish_call(identity.run_id, identity.worker_token, call_id, **kwargs)

    def ensure_active(self, identity):
        try:
            with ledger.SessionLocal.begin() as session:
                run, grant, work = ledger._locked(session, identity.run_id)
                ledger._active(run, grant, work, identity.worker_token, datetime.now(timezone.utc))
        except RunConflictError:
            raise credentials.GatewayUnauthorized() from None


class MockTransport:
    mode = 'mock'

    def invoke(self, body, *, deadline):
        if datetime.now(timezone.utc) >= deadline:
            raise GatewayUpstreamUnknown()
        # No fabricated provider usage: no real model was called. Missing usage
        # intentionally closes the grant to further NEW calls under the A policy.
        return {'message': {'role': 'assistant', 'content': 'RepoPilot mock response; no model was called.'},
                'usage': None}


class GatewayExchange:
    def __init__(self, *, store=None, artifact_store=None, transport=None, run_id=None, worker_token=None):
        self.store = store if store is not None else DatabaseGatewayStore()
        self.artifacts = artifact_store if artifact_store is not None else GatewayArtifactStore()
        self.transport = transport if transport is not None else MockTransport()
        if self.transport.mode not in ('mock', 'dashscope_fake'):
            raise ValueError('Live upstream is not enabled')
        if (run_id is None) != (worker_token is None):
            raise ValueError('Gateway scope requires both Run and attempt')
        self.run_id, self.worker_token = run_id, worker_token

    def authenticate(self, secret):
        identity = self.store.authenticate(secret)
        if (identity.mode != self.transport.mode or (self.run_id is not None
                and (identity.run_id != self.run_id or identity.worker_token != self.worker_token))):
            raise credentials.GatewayUnauthorized()
        return identity

    def _response(self, identity, record):
        result = dict(call_id=record['call_id'], status=record['status'], transport=record['transport'],
                      request_sha256=record['request_sha256'], usage=record['usage'], error_code=record['error_code'])
        if record['status'] == 'succeeded':
            try:
                saved = self.artifacts.read(identity.run_id, record['result_sha256'])
                if (saved['call_id'] != record['call_id'] or saved['transport'] != record['transport']
                        or saved['request_sha256'] != record['request_sha256']):
                    raise ValueError('Result artifact binding differs')
                result['message'] = saved['message']
                for key in ('finish_reason', 'truncated', 'usage_source'):
                    if key in saved:
                        result[key] = saved[key]
            except (ValueError, OSError, KeyError):
                raise GatewayArtifactUnavailable() from None
        return result

    def call(self, identity, data):
        request = ModelCallRequest.model_validate(data)
        body = forwarded_body(identity.policy, request)
        if self.transport.mode != 'mock':
            self.transport.validate(body)  # Reject unsupported models before spending quota.
        record = self.store.reserve(identity, request.model_dump(mode='json'))
        if record['transport'] != identity.mode:
            raise RunConflictError('Call transport differs from authorized mode')
        if not record['created']:
            return self._response(identity, record)  # Reserved/dispatched/unknown NEVER cause another send.
        dispatched = False
        known_usage = None
        try:
            request_hash = self.artifacts.write(identity.run_id, 'requests', body)
            if request_hash != record['request_sha256']:
                raise ValueError('Forwarded request differs from ledger')
            self.store.dispatch(identity, request.call_id)
            dispatched = True
            # No open database transaction here. Only these exact bounded bytes
            # may be supplied to a future fixed upstream transport.
            reply = self.transport.invoke(body_bytes(body), deadline=record['deadline'])
            if self.transport.mode == 'dashscope_fake':
                known_usage = reply.get('usage')
            if datetime.now(timezone.utc) >= record['deadline']:
                raise GatewayUpstreamUnknown()
            message = reply['message']
            if (set(message) != {'role', 'content'} or message['role'] != 'assistant'
                    or not isinstance(message['content'], str) or not message['content'].strip()
                    or len(message['content'].encode('utf-8')) > 131072):
                raise ValueError('Unsupported upstream response')
            if self.transport.mode == 'mock' and reply.get('usage') is not None:
                raise ValueError('Mock transport must not fabricate provider usage')
            saved = dict(
                call_id=request.call_id, transport=identity.mode, request_sha256=request_hash,
                message=message, usage=reply.get('usage'))
            for key in ('finish_reason', 'truncated', 'usage_source'):
                if key in reply:
                    saved[key] = reply[key]
            response_hash = self.artifacts.write(identity.run_id, 'responses', saved)
        except Exception as exc:
            # Store only controlled codes, never raw exceptions/request headers.
            # Even pre-dispatch failures retain the conservatively reserved quota.
            code = 'attempt_ended'
            if dispatched:
                code = (exc.code if isinstance(exc, UpstreamFailure)
                        else 'upstream_timeout' if isinstance(exc, (TimeoutError, GatewayUpstreamUnknown))
                        else 'invalid_upstream_response' if isinstance(exc, (ValueError, KeyError, TypeError))
                        else 'upstream_disconnected')
            self.store.finish(identity, request.call_id, status='unknown', error_code=code,
                              usage=exc.usage if isinstance(exc, UpstreamFailure) else known_usage)
            raise GatewayUpstreamUnknown() from None
        settled = self.store.finish(identity, request.call_id, status='succeeded',
                                    usage=reply.get('usage'), error_code=reply.get('error_code'),
                                    result_sha256=response_hash)
        self.store.ensure_active(identity)  # Late evidence stays stored; no delivery to a revoked attempt.
        return self._response(identity, settled)
