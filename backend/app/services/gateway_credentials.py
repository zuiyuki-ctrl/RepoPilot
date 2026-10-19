"""Trusted-worker issuance only. Never register these functions as business API routes."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import re
import secrets
from uuid import UUID
from pydantic import SecretStr
from sqlalchemy import select
from ..db.session import SessionLocal
from ..db.models import RunModelGrant
from ..schemas.model_gateway import ModelPolicy
from . import model_gateway_service as ledger
from .run_lifecycle import RunConflictError


class GatewayUnauthorized(Exception):
    """Public response must not distinguish unknown, expired, revoked, or cross-Run tokens."""


@dataclass(frozen=True)
class IssuedCredential:
    secret: SecretStr = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True)
class GatewayIdentity:
    run_id: UUID
    worker_token: UUID = field(repr=False)
    config_sha256: str
    expires_at: datetime
    policy: ModelPolicy
    mode: str


def credential_digest(secret):
    if not isinstance(secret, str) or not re.fullmatch(r'rpgw_[A-Za-z0-9_-]{43}', secret):
        raise GatewayUnauthorized()
    return hashlib.sha256(secret.encode('ascii')).hexdigest()


def issue_credential(run_id, worker_token, *, mode):
    # Called only by trusted worker after explicit runtime preflight, never public API.
    if mode not in ('mock', 'dashscope_fake', 'dashscope_live'):
        raise ValueError('Live gateway mode is not implemented')
    with SessionLocal.begin() as session:
        run, grant, work = ledger._locked(session, run_id)
        ledger._active(run, grant, work, worker_token, datetime.now(timezone.utc))
        if grant.credential_sha256 is not None or grant.gateway_mode is not None or grant.calls_reserved:
            raise RunConflictError('Credential already issued; never rotate/replay an uncertain attempt')
        secret = 'rpgw_' + secrets.token_urlsafe(32)
        grant.credential_sha256, grant.gateway_mode = credential_digest(secret), mode
        return IssuedCredential(SecretStr(secret), grant.expires_at)


def authenticate(secret):
    hashed = credential_digest(secret)
    with SessionLocal.begin() as session:
        run_id = session.scalar(select(RunModelGrant.run_id).where(RunModelGrant.credential_sha256 == hashed))
        if run_id is None:
            raise GatewayUnauthorized()
        try:
            run, grant, work = ledger._locked(session, run_id)
            if not grant.credential_sha256 or not hmac.compare_digest(grant.credential_sha256, hashed):
                raise GatewayUnauthorized()
            ledger._active(run, grant, work, grant.worker_token, datetime.now(timezone.utc))
            if grant.gateway_mode not in ('mock', 'dashscope_fake', 'dashscope_live'):
                raise GatewayUnauthorized()
            return GatewayIdentity(run.id, grant.worker_token, grant.config_sha256, grant.expires_at,
                                   ModelPolicy.model_validate(grant.policy), grant.gateway_mode)
        except RunConflictError:
            raise GatewayUnauthorized() from None
