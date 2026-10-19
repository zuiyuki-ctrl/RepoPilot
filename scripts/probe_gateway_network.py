"""Module B1: real Docker network checkpoint, with no DB, .env or model access.

Creates only UUID-labelled disposable resources; no builds/pulls, existing Docker
networks/containers or daemon firewall settings are changed. The one public probe
is a TCP handshake to 1.1.1.1:443; no model endpoint, secret or repository content
is sent. A temporary host canary returns a constant marker, never serves files.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import threading
import time
from uuid import uuid4
from .gateway_probe_runtime import Handler

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(__file__).with_name('gateway_probe_runtime.py').resolve()
LABEL = 'repopilot.gateway_probe'
ISOLATED = {'com.docker.network.bridge.gateway_mode_ipv4': 'isolated',
            'com.docker.network.bridge.gateway_mode_ipv6': 'isolated'}


class ProbeError(RuntimeError):
    pass


class CanaryHandler(Handler):
    def do_POST(self):
        self.respond(405)  # Host canary never initiates any outbound connection.


def docker(*args):
    result = subprocess.run(['docker', *args], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=20)
    if result.returncode:
        # No arbitrary daemon error/host environment in exported report.
        raise ProbeError('docker_command_failed')
    return result.stdout.strip()


def inspect_owned(kind, name, owner):
    # Failed inventory is NOT evidence that a resource has been removed.
    listed = docker(kind, 'ls', *(['--all'] if kind == 'container' else []),
                    '--filter', f'name={name}', '--format', '{{.Names}}' if kind == 'container' else '{{.Name}}')
    if name not in listed.splitlines():
        return None
    item = json.loads(docker(kind, 'inspect', name))[0]
    labels = item.get('Config', {}).get('Labels') if kind == 'container' else item.get('Labels')
    if (labels or {}).get(LABEL) != owner:
        raise ProbeError('resource_ownership_mismatch')
    return item


def create_args(name, owner, network, image, mode):
    source = str(RUNTIME)
    if ',' in source or '\n' in source:
        raise ProbeError('unsupported_mount_path')
    return ['container', 'create', '--pull=never', '--name', name, '--label', f'{LABEL}={owner}',
        '--network', network, '--read-only', '--user', '10001:10001', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--pids-limit', '64', '--memory', '128m', '--cpus', '0.5',
        '--log-driver', 'none', '--no-healthcheck', '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m',
        '--mount', f'type=bind,source={source},target=/probe.py,readonly', '--workdir', '/tmp',
        '--entrypoint', 'python', *(['--network-alias', 'mock-upstream'] if mode == 'upstream' else []),
        image, '-I', '-B', '/probe.py', mode]


def summarize(checks, cleanup_confirmed, error_code=None):
    if not cleanup_confirmed:
        return 'cleanup_unconfirmed'
    # Failure to reach a target in the positive control cannot prove isolation.
    if any(c['group'] == 'deny' and c['observed'] is True for c in checks):
        return 'failed'
    if error_code:
        return 'inconclusive'
    if any(c['observed'] != c['expected'] for c in checks) or not checks:
        return 'inconclusive'
    return 'passed'


class Probe:
    def __init__(self, image):
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
            raise ValueError('Use an existing immutable Python image ID')
        self.image, self.owner = image, uuid4().hex
        self.prefix = f'repopilot-gw-probe-{self.owner}'
        self.resources, self.checks = [], []

    def network(self, suffix, internal):
        name = f'{self.prefix}-{suffix}'
        self.resources.append(('network', name))  # Also covers create/CLI timeout gaps.
        args = ['network', 'create', '--driver', 'bridge', '--label', f'{LABEL}={self.owner}']
        if internal:
            args.append('--internal')
            for key, value in ISOLATED.items():
                args.extend(['--opt', f'{key}={value}'])
        docker(*args, name)
        item = inspect_owned('network', name, self.owner)
        if (not item or item.get('Driver') != 'bridge' or item.get('Internal') != internal
                or item.get('EnableIPv6') or (internal and any(item.get('Options', {}).get(k) != v for k,v in ISOLATED.items()))):
            raise ProbeError('network_configuration_mismatch')
        return name

    def container(self, suffix, network, mode):
        name = f'{self.prefix}-{suffix}'
        self.resources.append(('container', name))
        docker(*create_args(name, self.owner, network, self.image, mode))
        return name

    def check(self, name, group, container, kind, host='', port=0, expected=True):
        raw = docker('exec', '--user', '10001:10001', container,
                     'python', '-I', '-B', '/probe.py', 'check', kind, host, str(port))
        value = json.loads(raw)['reachable']
        if type(value) is not bool:
            raise ProbeError('invalid_probe_result')
        self.checks.append(dict(name=name, group=group, expected=expected, observed=value))
        print(f'{name}: {"ok" if value == expected else "MISMATCH"}', flush=True)
        return value

    def ready(self, container, port):
        for _ in range(15):
            result = json.loads(docker('exec', container, 'python', '-I', '/probe.py',
                                      'check', 'http', '127.0.0.1', str(port)))
            if result['reachable']:
                return
            time.sleep(0.2)
        raise ProbeError('mock_service_not_ready')

    def cleanup(self):
        errors = []
        # Containers first, then networks. Remove only exact names with our label.
        for kind in ('container', 'network'):
            for resource_kind, name in reversed(self.resources):
                if kind != resource_kind:
                    continue
                try:
                    if inspect_owned(kind, name, self.owner) is not None:
                        docker(kind, 'rm', *(['--force', '--volumes'] if kind == 'container' else []), name)
                    if inspect_owned(kind, name, self.owner) is not None:
                        raise ProbeError('removal_unconfirmed')
                except (ProbeError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
                    errors.append(dict(kind=kind, name=name, error_code=type(exc).__name__))
        return errors

    def run(self):
        report = dict(schema_version=1, probe_id=self.owner, image=self.image,
                      started_at=datetime.now(timezone.utc).isoformat(), checks=self.checks,
                      scope='IPv4 representative TCP/DNS probes; not a general sandbox security proof',
                      runtime_sha256=hashlib.sha256(RUNTIME.read_bytes()).hexdigest())
        canary = None
        thread = None
        error = None
        try:
            version = json.loads(docker('version', '--format', '{{json .Server}}'))
            report['engine'] = dict(version=version['Version'], os=version['Os'])
            if version['Os'] != 'linux' or int(version['Version'].split('.')[0]) < 28:
                raise ProbeError('linux_engine_28_required')
            if docker('image', 'inspect', '--format', '{{.Id}}', self.image) != self.image:
                raise ProbeError('image_identity_mismatch')
            internal = self.network('internal', True)
            outside = self.network('mock-egress', False)
            upstream = self.container('upstream', outside, 'upstream')
            # Alias is platform-fixed, not supplied by Agent.
            gateway = self.container('gateway', outside, 'gateway')
            docker('network', 'connect', '--alias', 'model-gateway', internal, gateway)
            agent = self.container('agent', internal, 'idle')
            offline = self.container('test-none', 'none', 'idle')
            for name in (upstream, gateway, agent, offline):
                docker('container', 'start', name)
            self.ready(upstream, 8888); self.ready(gateway, 8080)
            agent_info = inspect_owned('container', agent, self.owner)
            if (set(agent_info['NetworkSettings']['Networks']) != {internal}
                    or agent_info['HostConfig']['Privileged'] or agent_info['HostConfig']['PortBindings']
                    or agent_info['Config']['User'] != '10001:10001'
                    or not agent_info['HostConfig']['ReadonlyRootfs']
                    or any(m['Destination'] not in ('/probe.py', '/tmp') for m in agent_info['Mounts'])
                    or len([m for m in agent_info['Mounts'] if m['Type'] == 'bind'
                            and m['Destination'] == '/probe.py' and not m['RW']]) != 1):
                raise ProbeError('agent_isolation_configuration_mismatch')
            if inspect_owned('container', offline, self.owner)['HostConfig']['NetworkMode'] != 'none':
                raise ProbeError('platform_tests_must_remain_offline')
            upstream_ip = inspect_owned('container', upstream, self.owner)['NetworkSettings']['Networks'][outside]['IPAddress']
            gateway_ip = inspect_owned('container', gateway, self.owner)['NetworkSettings']['Networks'][internal]['IPAddress']
            # A constant-response canary proves the host is listening; not a file server.
            canary = ThreadingHTTPServer(('0.0.0.0', 0), CanaryHandler)
            canary.daemon_threads = True
            thread = threading.Thread(target=canary.serve_forever, daemon=True); thread.start()
            host_port = canary.server_port
            self.check('gateway_to_mock', 'control', gateway, 'http', 'mock-upstream', 8888)
            self.check('agent_via_gateway_to_mock', 'allow', agent, 'gateway', 'model-gateway', 8080)
            self.check('gateway_rejects_connect_proxy', 'allow', agent, 'reject_proxy', 'model-gateway', 8080)
            self.check('host_canary_positive_control', 'control', gateway, 'http', 'host.docker.internal', host_port)
            self.check('public_tcp_positive_control', 'control', gateway, 'tcp', '1.1.1.1', 443)
            self.check('external_dns_positive_control', 'control', gateway, 'dns', 'example.com')
            for port, label in ((8888, 'upstream'), (8000, 'business_api_canary'), (5432, 'database_canary')):
                self.check(f'{label}_positive_control', 'control', gateway, 'tcp', upstream_ip, port)
                self.check(f'agent_direct_{label}', 'deny', agent, 'tcp', upstream_ip, port, expected=False)
            self.check('agent_host_canary', 'deny', agent, 'tcp', 'host.docker.internal', host_port, expected=False)
            self.check('agent_public_tcp', 'deny', agent, 'tcp', '1.1.1.1', 443, expected=False)
            self.check('agent_external_dns', 'deny', agent, 'dns', 'example.com', expected=False)
            self.check('agent_docker_socket', 'deny', agent, 'socket_mount', expected=False)
            self.check('test_none_to_gateway', 'deny', offline, 'tcp', gateway_ip, 8080, expected=False)
            self.check('test_none_to_public', 'deny', offline, 'tcp', '1.1.1.1', 443, expected=False)
        except (ProbeError, OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
            error = str(exc) if isinstance(exc, ProbeError) else type(exc).__name__
        finally:
            if canary:
                canary.shutdown(); canary.server_close()
            if thread:
                thread.join(timeout=3)
            cleanup_errors = self.cleanup()
            report.update(error_code=error, cleanup_confirmed=not cleanup_errors,
                          cleanup_errors=cleanup_errors, completed_at=datetime.now(timezone.utc).isoformat())
            report['status'] = summarize(self.checks, not cleanup_errors, error)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='Existing immutable Python 3.11+ image ID')
    parser.add_argument('--execute', action='store_true', help='Create temporary labelled Docker resources and a host canary')
    args = parser.parse_args()
    if not args.execute:
        parser.error('Explicit --execute is required; no resources created')
    probe = Probe(args.image)
    report = probe.run()
    directory = ROOT / '.platform-artifacts' / 'gateway-network'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{probe.owner}.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(f'Status: {report["status"]}; cleanup_confirmed={report["cleanup_confirmed"]}\nReport: {path}')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
