"""Owned, bounded, offline Docker execution. Never pulls images or starts a host shell."""
import json
import re
import subprocess
from threading import Thread
from uuid import UUID
from .process_output import CapturedOutput, drain_text_stream


class ContainerUnconfirmed(RuntimeError):
    pass


def container_name(run_id, purpose):
    if purpose not in ('agent', 'baseline', 'final'):
        raise ValueError('Unknown container purpose')
    return f'repopilot-v2-{UUID(str(run_id)).hex}-{purpose}'


def docker(*args):
    return subprocess.run(['docker', *args], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=30, check=False)


def inspect_container(name):
    # A failed inspect is not proof of absence (daemon could be unavailable).
    listed = docker('container', 'ls', '--all', '--filter', f'name=^/{name}$', '--format', '{{.Names}}')
    if listed.returncode:
        raise ContainerUnconfirmed('Docker inventory unavailable')
    if name not in listed.stdout.splitlines():
        return None
    result = docker('container', 'inspect', name)
    if result.returncode:
        raise ContainerUnconfirmed('Container identity unavailable')
    return json.loads(result.stdout)[0]


def remove_owned(run_id, purpose):
    name = container_name(run_id, purpose)
    current = inspect_container(name)
    if current is None:
        return
    if (current.get('Config', {}).get('Labels') or {}).get('repopilot.run_id') != str(run_id):
        raise ContainerUnconfirmed('Container ownership mismatch')
    if docker('container', 'rm', '--force', '--volumes', name).returncode or inspect_container(name) is not None:
        raise ContainerUnconfirmed('Container removal unconfirmed')


def run_container(run_id, purpose, *, image, argv, mounts, workdir, timeout_seconds):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise ValueError('Existing immutable Docker image ID required')
    if not argv or any(not isinstance(arg, str) or '\x00' in arg for arg in argv):
        raise ValueError('Argument array required')
    name = container_name(run_id, purpose)
    if inspect_container(name) is not None:
        raise ContainerUnconfirmed('Container already exists; inspect and recover, do not replay')
    checked = docker('image', 'inspect', '--format', '{{.Id}}', image)
    if checked.returncode or checked.stdout.strip() != image:
        raise ValueError('Required local image unavailable')
    command = ['container', 'create', '--pull=never', '--name', name,
        '--label', f'repopilot.run_id={run_id}', '--network', 'none', '--read-only',
        '--user', '10001:10001', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--pids-limit', '128', '--memory', '512m', '--cpus', '1',
        '--log-driver', 'none', '--no-healthcheck', '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
        '--workdir', workdir, '--entrypoint', argv[0]]
    for path, target, readonly in mounts:
        absolute = str(path.resolve(strict=True))
        if ',' in absolute or '\n' in absolute:
            raise ValueError('Unsupported mount path')
        command.extend(['--mount', f'type=bind,source={absolute},target={target}' + (',readonly' if readonly else '')])
    command.extend([image, *argv[1:]])
    process = None
    captures = [CapturedOutput(), CapturedOutput()]
    threads = []
    timed_out = False
    try:
        created = docker(*command)
        if created.returncode:
            raise RuntimeError('Container create failed')
        process = subprocess.Popen(['docker', 'container', 'start', '--attach', name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        for stream, capture in zip((process.stdout, process.stderr), captures):
            thread = Thread(target=drain_text_stream,
                kwargs=dict(stream=stream, captured=capture, max_chars=50_000), daemon=True)
            thread.start()
            threads.append(thread)
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
        if not timed_out:
            state = inspect_container(name)
            if state is None or state['State']['Running'] or state['State']['Status'] != 'exited':
                raise ContainerUnconfirmed('Container has not exited')
            exit_code = state['State']['ExitCode']
        else:
            exit_code = None
    finally:
        # Includes create/start/inspect errors. Never call a generic rm on an unowned name.
        try:
            remove_owned(run_id, purpose)
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            for thread in threads:
                thread.join(timeout=10)
            if any(thread.is_alive() for thread in threads):
                raise ContainerUnconfirmed('Container output drain unconfirmed')
    if any(c.error for c in captures):
        raise RuntimeError('Container output read failed')
    return dict(exit_code=exit_code, timed_out=timed_out, writers_stopped=True,
                stdout=captures[0].get_text(), stderr=captures[1].get_text(),
                stdout_truncated=captures[0].truncated, stderr_truncated=captures[1].truncated)
