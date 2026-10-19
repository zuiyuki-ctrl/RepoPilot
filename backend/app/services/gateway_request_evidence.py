"""On-demand historical request preview, never a workspace reconstruction.

Only terminal Runs with revoked credentials can expose text. Redaction is a
bounded, versioned pattern filter, not a general secret/DLP guarantee.
"""
import hashlib
import os
from pathlib import Path
import re
from uuid import UUID

from sqlalchemy import select
from ..core.config import PROJECT_ROOT
from ..db.session import SessionLocal
from ..db.models import PlatformRun
from ..db.models.model_gateway import ModelCall, RunModelGrant
from ..schemas.model_gateway import ModelPolicy, ModelCallRequest, body_bytes, forwarded_body
from . import platform_artifacts as artifacts
from .repository_scanner import _is_link_or_reparse_point

MAX_ARTIFACT_BYTES = 300000
MAX_MESSAGE_CHARS = 4000
MAX_PREVIEW_CHARS = 16000
REDACTION_VERSION = 'credential-patterns-v1'
SECRET = re.compile(r'rpgw_[A-Za-z0-9_-]{43}|\bsk-[A-Za-z0-9_-]{8,}|\bBearer\s+[A-Za-z0-9._~+/=-]+', re.IGNORECASE)


def read_request(run_id, digest):
    """No directory creation; only fixed ledger-derived filename, no user paths."""
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Invalid request reference')
    root = Path(os.getenv('PLATFORM_ARTIFACT_ROOT', str(PROJECT_ROOT / '.platform-artifacts'))).absolute()
    directory = root / str(UUID(str(run_id))) / 'gateway' / 'requests'
    # Check all ancestors, including Windows reparse points, before opening.
    for parent in reversed((directory, *directory.parents)):
        if _is_link_or_reparse_point(parent) or not parent.is_dir():
            raise ValueError('Unsafe request directory')
    raw = artifacts.read_bytes(directory / f'{digest}.json', limit=MAX_ARTIFACT_BYTES)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Request digest mismatch')
    return raw


def project_request(raw, policy):
    body = artifacts.decode_json(raw)
    if not isinstance(body, dict):
        raise ValueError('Invalid request')
    frozen = ModelPolicy.model_validate(policy)
    request = ModelCallRequest.model_validate(dict(call_id='preview', messages=body.get('messages')))
    expected = forwarded_body(frozen, request)
    # Exact canonical bytes also verify allowed fields and frozen parameters.
    if body_bytes(expected) != raw:
        raise ValueError('Request differs from frozen policy')
    budget, messages = MAX_PREVIEW_CHARS, []
    redacted = truncated = False
    for index, message in enumerate(request.messages):
        # Redact BEFORE truncating, including credentials crossing the boundary.
        safe, replacements = SECRET.subn('[REDACTED]', message.content)
        limit = min(MAX_MESSAGE_CHARS, budget)
        preview = safe[:limit]
        cut = len(safe) > limit
        budget -= len(preview)
        redacted |= replacements > 0
        truncated |= cut
        messages.append(dict(index=index, role=message.role, content=preview,
            original_chars=len(message.content), displayed_chars=len(preview),
            redacted=replacements > 0, truncated=cut))
    return dict(parameters={key: value for key, value in expected.items() if key != 'messages'},
        messages=messages, message_count=len(messages), original_bytes=len(raw),
        redacted=redacted, truncated=truncated,
        display_status='redacted_and_truncated' if redacted and truncated else
            'redacted' if redacted else 'truncated' if truncated else 'unchanged',
        redaction_version=REDACTION_VERSION)


def get_request_evidence(run_id, call_id):
    with SessionLocal() as session:
        # Bind platform call UUID to Run in SQL; a foreign call is indistinguishable
        # from a missing one. Never accept the Agent-controlled idempotency key.
        call = session.scalar(select(ModelCall).where(ModelCall.id == call_id, ModelCall.run_id == run_id))
        if call is None:
            return None
        run = session.get(PlatformRun, run_id)
        grant = session.get(RunModelGrant, run_id)
        if run is None:
            return None
        result = dict(run_id=str(run_id), call_id=str(call.id), request_sha256=call.request_sha256,
            status='withheld', hash_verified=False, preview=None,
            dispatch_recorded=call.dispatched_at is not None,
            limitations=['Preview is escaped text, not executable instructions',
                'Redaction covers recognised credential patterns only, not arbitrary encoded secrets',
                'SHA256 refers to original bytes, not the redacted/truncated preview',
                'A stored/dispatched request does not prove provider receipt or model understanding'])
        if (run.lifecycle not in ('finished', 'interrupted') or grant is None
                or grant.revoked_at is None or grant.credential_sha256 is not None):
            return result
        digest, policy = call.request_sha256, grant.policy
    try:
        raw = read_request(run_id, digest)
        result['hash_verified'] = True
        result['preview'] = project_request(raw, policy)
        result['status'] = 'recorded'
    except FileNotFoundError:
        result['status'] = 'missing'
    except OSError:
        result['status'] = 'unavailable'
    except (ValueError, TypeError):
        result['status'] = 'invalid'
    return result
