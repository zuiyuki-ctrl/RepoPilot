"""End-to-end TLS through the fixed relay; fake and explicit live factories.

The acceptance factory only accepts the public fake credential and an explicit
test CA. Live uses the image CA bundle and a mounted credential file.
Neither Agent input nor environment variables select URL, CA or secret content.
"""
import os
from pathlib import Path
import ssl
import stat

import httpx
from pydantic import SecretStr

from .gateway_upstream import DashScopeProtocolTransport, ENDPOINT
from .repository_scanner import _is_link_or_reparse_point

PROXY_URL = 'http://provider-egress:8081'
FAKE_SECRET = 'repopilot-fake-upstream-only'


def read_mounted_secret(path: Path) -> SecretStr:
    """Read one bounded RO regular file; never include its value/path in errors."""
    try:
        path = Path(path)
        if not path.is_absolute() or any(_is_link_or_reparse_point(p) for p in (path, *path.parents)):
            raise ValueError()
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 256:
            raise ValueError()
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                             | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_size > 256 or info.st_mode & 0o222):
                raise ValueError()
            raw = stream.read(257)
        if len(raw) > 256:
            raise ValueError()
        # Permit a single trailing newline, not whitespace/embedded header controls.
        value = raw.removesuffix(b'\n').removesuffix(b'\r').decode('ascii')
        if not 16 <= len(value) <= 240 or any(not 33 <= ord(c) <= 126 for c in value):
            raise ValueError()
        return SecretStr(value)
    except (OSError, ValueError, UnicodeError):
        raise ValueError('Invalid mounted provider credential') from None


class FixedProxyTLSAdapter(httpx.AsyncBaseTransport):
    def __init__(self, context: ssl.SSLContext):
        if (not isinstance(context, ssl.SSLContext) or not context.check_hostname
                or context.verify_mode != ssl.CERT_REQUIRED
                or context.minimum_version < ssl.TLSVersion.TLSv1_2):
            raise ValueError('Verified TLS required')
        self._transport = httpx.AsyncHTTPTransport(verify=context, proxy=PROXY_URL,
            trust_env=False, retries=0, http1=True, http2=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0))

    async def handle_async_request(self, request):
        if request.method != 'POST' or str(request.url) != ENDPOINT:
            raise ValueError('Fixed upstream endpoint required')
        return await self._transport.handle_async_request(request)

    async def aclose(self):
        await self._transport.aclose()


def fake_tls_transport(*, ca_file: Path, credential_file: Path) -> DashScopeProtocolTransport:
    secret = read_mounted_secret(credential_file)
    if secret.get_secret_value() != FAKE_SECRET:
        raise ValueError('Live provider credentials are not enabled')
    # Explicit CA bypasses SSL_CERT_FILE/DIR; hostname remains the fixed supplier.
    context = ssl.create_default_context(cafile=str(ca_file))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return DashScopeProtocolTransport(adapter=FixedProxyTLSAdapter(context))


class LiveDashScopeTransport(DashScopeProtocolTransport):
    """Trusted construction only. SecretStr stays out of artifacts and errors."""
    mode = 'dashscope_live'
    usage_source = 'provider'

    def __init__(self, *, adapter, secret: SecretStr):
        super().__init__(adapter=adapter)
        if not isinstance(secret, SecretStr) or secret.get_secret_value() == FAKE_SECRET:
            raise ValueError('A mounted live credential is required')
        self._secret = secret

    def authorization(self):
        return 'Bearer ' + self._secret.get_secret_value()


def live_tls_transport(*, credential_file: Path) -> LiveDashScopeTransport:
    import certifi
    # Use the image's CA bundle, not environment-selected roots or fixture CAs.
    context = ssl.create_default_context(cafile=certifi.where())
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return LiveDashScopeTransport(adapter=FixedProxyTLSAdapter(context),
                                 secret=read_mounted_secret(credential_file))
