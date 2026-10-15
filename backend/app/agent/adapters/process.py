"""Offline external executable adapter; neither plans nor scores the task."""
from .base import StepResult
from ...schemas.platform_run import AgentRunResult
from ...schemas.process_agent import ProcessConfiguration, ProcessTraceEvent
from ...services import platform_artifacts as artifacts
from ...services.platform_test_collector import checked_bundle
from ...services.platform_container import run_container, remove_owned
from ...services.experiment_contract_service import digest


def parse_result(path, request, exit_code):
    result = AgentRunResult.model_validate(artifacts.decode_json(artifacts.read_bytes(path)))
    if result.run_id != request.run_id or result.agent != request.agent:
        raise ValueError('Result identity mismatch')
    if result.execution_status not in ('completed', 'failed'):
        raise ValueError('Offline Process v1 only reports completed or failed')
    return result, ('failed' if exit_code != 0 else result.execution_status)


def read_trace(path, request, declared):
    if not path.exists() and not path.is_symlink():
        return {'status': 'missing' if declared else 'unsupported', 'events': []}
    try:
        lines = artifacts.read_bytes(path).splitlines()
        if len(lines) > 1000:
            raise ValueError('Trace line limit exceeded')
        events, seen, calls = [], {}, set()
        for line in lines:
            event = ProcessTraceEvent.model_validate(artifacts.decode_json(line))
            if event.run_id != str(request.run_id):
                raise ValueError('Trace run mismatch')
            value = event.model_dump(mode='json')
            if event.event_id in seen:
                if seen[event.event_id] != value:
                    raise ValueError('Conflicting duplicate trace event')
                continue
            if event.kind == 'model_call' and event.call_id in calls:
                raise ValueError('Duplicate model call usage')
            if event.kind == 'model_call':
                calls.add(event.call_id)
            seen[event.event_id] = value
            events.append(value)
        # No expected call count available: never claim complete coverage.
        return {'status': 'partial' if events else 'missing', 'events': events}
    except (ValueError, OSError, RecursionError):
        return {'status': 'invalid', 'events': []}


class ProcessAdapter:
    def __init__(self):
        self.run_id = None

    def metadata(self):
        return {'name': 'Offline Process Adapter', 'protocol_version': 1, 'adapter': 'process'}

    def prepare(self, request, state):
        self.run_id = request.run_id
        directory, manifest, before = checked_bundle(request, state)
        config = ProcessConfiguration.model_validate(manifest['process_config'])
        if (digest(config.model_dump(mode='json')) != request.config_sha256
                or request.agent.implementation_sha256 != config.image.removeprefix('sha256:')):
            raise ValueError('Frozen process identity differs')
        if artifacts.inventory(directory / 'workspace') != before:
            raise ValueError('Process workspace changed before execution')
        if request.budget.token_enforcement == 'enforced' or request.budget.max_tool_calls is not None:
            raise ValueError('Black box cannot enforce model/tool count budgets')
        (directory / 'input').mkdir()
        artifacts.write_json(directory / 'input' / 'request.json', request.model_dump(mode='json'))
        (directory / 'output').mkdir()
        (directory / 'output').chmod(0o777)
        return StepResult(state=state, next_stage='process_run')

    def run(self, request, stage, state):
        self.run_id = request.run_id
        if stage != 'process_run':
            raise ValueError('Unknown process stage')
        directory, manifest, _ = checked_bundle(request, state)
        config = ProcessConfiguration.model_validate(manifest['process_config'])
        execution = run_container(request.run_id, 'agent', image=config.image, argv=config.argv,
            mounts=[(directory / 'input', '/input', True), (directory / 'workspace', '/workspace', False),
                    (directory / 'output', '/output', False)], workdir='/workspace',
            timeout_seconds=request.budget.timeout_seconds)
        artifacts.write_json(directory / 'process-log.json', execution)
        info = {**execution, 'protocol_error': None}
        status = 'timed_out' if execution['timed_out'] else 'failed'
        if not execution['timed_out']:
            try:
                reported, status = parse_result(directory / 'output' / 'result.json', request, execution['exit_code'])
                info['reported_status'] = reported.execution_status
            except (ValueError, OSError, RecursionError):
                info['protocol_error'] = 'invalid_or_missing_result'
        info['trace'] = read_trace(directory / 'output' / 'trace.jsonl', request, config.trace)
        return StepResult(state={**state, 'process_execution': info}, execution_status=status)

    def cleanup(self):
        if self.run_id is not None:
            remove_owned(self.run_id, 'agent')
        return {'status': 'confirmed'}
