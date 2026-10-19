"""Opt-in, mock-only Process runtime. Docker resources belong to one fenced attempt.

The offline/test runner is deliberately unchanged. No image pulls, port publishing,
provider keys, Docker socket mounts, host networking or automatic replay here.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from . import platform_artifacts as artifacts
from .platform_container import docker, ContainerUnconfirmed
from .repository_scanner import _is_link_or_reparse_point

ISOLATED = {'com.docker.network.bridge.gateway_mode_ipv4': 'isolated',
            'com.docker.network.bridge.gateway_mode_ipv6': 'isolated'}
LABEL = 'repopilot.gateway_attempt'
URL = 'http://model-gateway:8080/v1/model-calls'
CREDENTIAL_TARGET = '/run/repopilot/credential'


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['mock']
    image: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    control_network: str = Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}$')
    database_file: Path


def safe_path(path, *, directory=False):
    path = Path(path).absolute()
    if any(_is_link_or_reparse_point(p) for p in (path, *path.parents)):
        raise ValueError('Gateway path must not be a link')
    if directory and not path.is_dir():
        raise ValueError('Gateway directory missing')
    if any(c in str(path) for c in (',', '\r', '\n', '\x00')):
        raise ValueError('Unsupported gateway mount path')
    return path.resolve(strict=True)


def load_settings():
    configured = os.environ.get('REPOPILOT_GATEWAY_RUNTIME_CONFIG')
    if not configured or not Path(configured).is_absolute():
        raise ValueError('model_gateway_runtime_not_configured')
    settings = RuntimeSettings.model_validate(artifacts.decode_json(
        artifacts.read_bytes(safe_path(configured), limit=8192)))
    if not settings.database_file.is_absolute():
        raise ValueError('Gateway database file must be absolute')
    # Check a regular, bounded file without exporting its contents. The gateway
    # validates the explicit DB-only schema; the Agent never receives this file.
    artifacts.read_bytes(safe_path(settings.database_file), limit=8192)
    return settings


def names(run_id, token):
    prefix = f'rpgw-{UUID(str(run_id)).hex}-{UUID(str(token)).hex}'
    return {kind: prefix + '-' + kind for kind in ('agent', 'gateway', 'network')}


def checked(*args):
    result = docker(*args)
    if result.returncode:
        raise ContainerUnconfirmed('Gateway Docker operation failed')
    return result.stdout.strip()


def inspect_owned(kind, name, run_id, token):
    listed = checked(kind, 'ls', *(['--all'] if kind == 'container' else []),
                     '--filter', f'name={name}', '--format', '{{.Names}}' if kind == 'container' else '{{.Name}}')
    if name not in listed.splitlines():
        return None
    item = json.loads(checked(kind, 'inspect', name))[0]
    labels = item.get('Config', {}).get('Labels') if kind == 'container' else item.get('Labels')
    if ((labels or {}).get(LABEL) != str(token)
            or (labels or {}).get('repopilot.run_id') != str(run_id)):
        raise ContainerUnconfirmed('Gateway resource ownership differs')
    return item


def isolated_network(item):
    return (item.get('Driver') == 'bridge' and item.get('Internal') is True
            and not item.get('EnableIPv6')
            and all(item.get('Options', {}).get(k) == v for k, v in ISOLATED.items()))


def preflight(settings, agent_image):
    version = json.loads(checked('version', '--format', '{{json .Server}}'))
    if version['Os'] != 'linux' or int(version['Version'].split('.')[0]) < 28:
        raise ValueError('Gateway requires Linux Docker Engine 28 or later')
    for image in (settings.image, agent_image):
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
            raise ValueError('Immutable local image required')
        if checked('image', 'inspect', '--format', '{{.Id}}', image) != image:
            raise ValueError('Gateway image identity differs')
        # Image VOLUME declarations would silently add unreviewed writable mounts.
        info = json.loads(checked('image', 'inspect', image))[0]
        if info.get('Config', {}).get('Volumes'):
            raise ValueError('Gateway/Agent images must not declare volumes')
    control = json.loads(checked('network', 'inspect', settings.control_network))[0]
    if not isolated_network(control):
        raise ValueError('Mock gateway control network must be internal and isolated')


def attempt_directory(run_id, token):
    root = safe_path(artifacts.run_directory(run_id), directory=True)
    path = root / ('.gateway-runtime-' + UUID(str(token)).hex)
    if path.exists() or path.is_symlink():
        safe_path(path, directory=True)
    return path


def private_directory(path):
    path.mkdir(mode=0o700)  # Never reuse a directory from an uncertain attempt.
    if os.name == 'nt':
        # chmod on Windows does not restrict readers. Set an explicit owner-only
        # inheritable DACL before writing any plaintext (SYSTEM is needed by Docker).
        sid = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
            '[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'],
            capture_output=True, text=True, timeout=15, check=True).stdout.strip()
        if not re.fullmatch(r'S-1-5-(?:[0-9]+-)*[0-9]+', sid):
            raise ValueError('Cannot establish private credential directory owner')
        result = subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
            f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'], capture_output=True, timeout=15)
        if result.returncode:
            raise ValueError('Cannot protect gateway credential directory')
    else:
        path.chmod(0o700)


def mount(path, target, readonly):
    return ['--mount', f'type=bind,source={safe_path(path)},target={target}'
            + (',readonly' if readonly else '')]


def create_args(name, run_id, token, network, image, argv, *, mounts, env=(), workdir='/tmp'):
    if not argv or any(not isinstance(a, str) or '\x00' in a for a in argv):
        raise ValueError('Argument array required')
    args = ['container', 'create', '--pull=never', '--name', name,
            '--label', f'{LABEL}={token}', '--label', f'repopilot.run_id={run_id}',
            '--network', network, '--read-only', '--user', '10001:10001', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--pids-limit', '128', '--memory', '512m',
            '--cpus', '1', '--log-driver', 'none', '--no-healthcheck',
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m', '--workdir', workdir,
            '--entrypoint', argv[0]]
    for path, target, readonly in mounts:
        args.extend(mount(path, target, readonly))
    for key, value in env:
        args.extend(['--env', f'{key}={value}'])
    return [*args, image, *argv[1:]]


def revoke_owned_attempt(run_id, token):
    from . import model_gateway_service as ledger
    from .run_lifecycle import RunConflictError
    with ledger.SessionLocal.begin() as session:
        run, grant, work = ledger._locked(session, run_id)
        if work.active_token != token or grant.worker_token != token:
            raise RunConflictError('Gateway cleanup lost worker ownership')
        ledger.revoke_attempt(session, run)


def cleanup_owned_attempt(run_id, token):
    """Revoke first; preserve the fence and secret if any confirmation is missing.

    Cleanup is deterministic from the claim, even if the child died between Docker
    create and saving state. Never remove the operator-owned control network/DB file.
    """
    errors = []
    try:
        revoke_owned_attempt(run_id, token)
    except Exception:
        errors.append('revocation_unconfirmed')
    resources = names(run_id, token)
    for kind, name in (('container', resources['agent']), ('container', resources['gateway']),
                       ('network', resources['network'])):
        try:
            if inspect_owned(kind, name, run_id, token) is not None:
                checked(kind, 'rm', *(['--force', '--volumes'] if kind == 'container' else []), name)
            if inspect_owned(kind, name, run_id, token) is not None:
                raise ContainerUnconfirmed('Gateway resource still exists')
        except Exception:
            errors.append('resource_cleanup_unconfirmed')
    if not errors:
        try:
            directory = attempt_directory(run_id, token)
            if directory.exists():
                # No recursive deletion, no globs. Only our one regular file.
                secret = directory / 'credential'
                if secret.exists() or secret.is_symlink():
                    artifacts.read_bytes(safe_path(secret), limit=128)
                    secret.chmod(0o600)
                    secret.unlink()
                directory.rmdir()  # Unexpected contents deliberately prevent success.
        except Exception:
            errors.append('credential_cleanup_unconfirmed')
    if errors:
        raise ContainerUnconfirmed('Gateway cleanup unconfirmed; retain worker fence')


def ensure_active(run_id, token):
    from . import model_gateway_service as ledger
    with ledger.SessionLocal.begin() as session:
        run, grant, work = ledger._locked(session, run_id)
        ledger._active(run, grant, work, token, datetime.now(timezone.utc))


HEALTH_CHECK = """import json,urllib.request
with urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=1) as response:
    assert json.load(response) == {'status':'ok','transport':'mock','model_access':False}
"""


def run_process(request, config, directory, token):
    """One complete mock attempt, with cleanup on every exit (including partial setup)."""
    settings = load_settings()
    run_id = request.run_id
    resources = names(run_id, token)
    started = time.monotonic()
    try:
        preflight(settings, config.image)
        for kind, name in (('container', resources['agent']), ('container', resources['gateway']),
                           ('network', resources['network'])):
            if inspect_owned(kind, name, run_id, token) is not None:
                raise ContainerUnconfirmed('Gateway attempt exists; recover, never replay')
        credential_dir = attempt_directory(run_id, token)
        private_directory(credential_dir)
        from .gateway_credentials import issue_credential
        issued = issue_credential(run_id, token, mode='mock')
        credential = credential_dir / 'credential'
        with credential.open('x', encoding='ascii') as stream:
            stream.write(issued.secret.get_secret_value())
        credential.chmod(0o444)  # Exact-file RO bind; private parent restricts host access.
        gateway_dir = directory / 'gateway'
        gateway_dir.mkdir(exist_ok=True)
        safe_path(gateway_dir, directory=True)
        gateway_dir.chmod(0o777)  # Container uid 10001, never mounted into Agent.
        args = ['network', 'create', '--driver', 'bridge', '--internal',
                '--label', f'{LABEL}={token}', '--label', f'repopilot.run_id={run_id}']
        for key, value in ISOLATED.items():
            args.extend(['--opt', f'{key}={value}'])
        checked(*args, resources['network'])
        network = inspect_owned('network', resources['network'], run_id, token)
        if not network or not isolated_network(network):
            raise ContainerUnconfirmed('Gateway Agent network differs')
        checked(*create_args(resources['gateway'], run_id, token, settings.control_network,
            settings.image, ['python', '-I', '-B', '/app/gateway_entrypoint.py'],
            mounts=[(settings.database_file, '/run/repopilot/database.json', True),
                    (gateway_dir, f'/evidence/{run_id}/gateway', False)],
            env=[('REPOPILOT_GATEWAY_RUN_ID', str(run_id)),
                 ('REPOPILOT_GATEWAY_ATTEMPT_ID', str(token))]))
        checked('network', 'connect', '--alias', 'model-gateway', resources['network'], resources['gateway'])
        checked('container', 'start', resources['gateway'])
        ready = False
        for _ in range(15):
            ensure_active(run_id, token)
            if docker('exec', resources['gateway'], 'python', '-I', '-c', HEALTH_CHECK).returncode == 0:
                ready = True
                break
            time.sleep(0.2)
        if not ready:
            raise RuntimeError('Mock gateway readiness failed')
        ensure_active(run_id, token)
        checked(*create_args(resources['agent'], run_id, token, resources['network'],
            config.image, config.argv, mounts=[(directory / 'input', '/input', True),
                (directory / 'workspace', '/workspace', False), (directory / 'output', '/output', False),
                (credential, CREDENTIAL_TARGET, True)], workdir='/workspace',
            env=[('REPOPILOT_MODEL_GATEWAY_URL', URL), ('REPOPILOT_MODEL_CREDENTIAL_FILE', CREDENTIAL_TARGET),
                 ('REPOPILOT_MODEL_TRANSPORT', 'mock')]))
        info = inspect_owned('container', resources['agent'], run_id, token)
        if (not info or set(info['NetworkSettings']['Networks']) != {resources['network']}
                or info['HostConfig'].get('PortBindings') or info['HostConfig'].get('Privileged')):
            raise ContainerUnconfirmed('Agent isolation configuration differs')
        checked('container', 'start', resources['agent'])
        timed_out, exit_code = False, None
        while True:
            info = inspect_owned('container', resources['agent'], run_id, token)
            if not info:
                raise ContainerUnconfirmed('Agent disappeared')
            if info['State']['Status'] == 'exited':
                exit_code = info['State']['ExitCode']
                break
            if (time.monotonic() - started >= request.budget.timeout_seconds
                    or datetime.now(timezone.utc) >= issued.expires_at):
                timed_out = True
                break
            ensure_active(run_id, token)
            time.sleep(0.2)
        # No attach/log capture: an Agent could print the readable bearer. C will
        # add reviewed gateway evidence; do not ingest arbitrary online trace yet.
        return dict(exit_code=exit_code, timed_out=timed_out, writers_stopped=True,
                    stdout='', stderr='', stdout_truncated=False, stderr_truncated=False,
                    output_policy='suppressed_for_gateway_credentials', gateway_mode='mock',
                    gateway_image=settings.image, model_access=False,
                    gateway_runtime_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    finally:
        cleanup_owned_attempt(run_id, token)
