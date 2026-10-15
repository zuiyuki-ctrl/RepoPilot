"""Trusted Day 3 development entry: freeze files/rules and enqueue, never calls a model."""
import argparse
from pathlib import Path
import subprocess
from uuid import UUID, uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository-id', type=UUID, required=True)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--definition', type=Path, required=True)
    parser.add_argument('--test-image', required=True, help='Existing immutable sha256 image ID')
    parser.add_argument('--process-config', type=Path)
    parser.add_argument('--task-id', type=UUID, help='Fresh Native plan task; exclusive with process-config')
    parser.add_argument('--agent-name', default='Protocol Demo (fixture)')
    parser.add_argument('--agent-version', default='v1')
    parser.add_argument('--creation-key', required=True)
    args = parser.parse_args()
    if bool(args.task_id) == bool(args.process_config):
        parser.error('Choose exactly one of --task-id and --process-config')
    from backend.app.db.session import SessionLocal
    from backend.app.db.models import Repository, AgentTask, PlatformRun
    from sqlalchemy import select
    from backend.app.schemas.experiment import ExperimentCase
    from backend.app.schemas.experiment_definition import AcceptanceRule
    from backend.app.schemas.platform_run import AgentRunRequest
    from backend.app.schemas.process_agent import ProcessConfiguration
    from backend.app.schemas.run_config import AgentRunConfig
    from backend.app.services import platform_artifacts as artifacts
    from backend.app.services.experiment_contract_service import digest
    from backend.app.services.platform_container import docker
    from backend.app.services.platform_test_collector import create_bundle, environment_fingerprint
    from backend.app.services.platform_run_service import create_run
    from backend.app.services.run_control_service import enqueue_native, enqueue_process

    with SessionLocal() as session:
        if session.scalar(select(PlatformRun.id).where(PlatformRun.creation_key == args.creation_key)):
            parser.error('Creation key already exists; inspect its Run, do not replay preparation')
        repository = session.get(Repository, args.repository_id)
        if repository is None or not repository.workspace_path:
            parser.error('Registered repository workspace required')
        workspace = Path(repository.workspace_path)
        task = session.get(AgentTask, args.task_id) if args.task_id else None
        if args.task_id and (task is None or task.repository_id != repository.id or task.status != 'created'):
            parser.error('Fresh matching Native task required')
        config = AgentRunConfig.model_validate(task.run_config) if task else None
    case = ExperimentCase.model_validate(artifacts.decode_json(artifacts.read_bytes(args.case)))
    definition = artifacts.decode_json(artifacts.read_bytes(args.definition))
    rule = AcceptanceRule.model_validate(definition.get('acceptance', definition))
    for command in (['git', '-C', str(workspace), 'rev-parse', 'HEAD'],
                    ['git', '-C', str(workspace), 'status', '--porcelain', '--untracked-files=all']):
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=True)
        if ('rev-parse' in command and result.stdout.strip() != case.repository_commit
                or 'status' in command and result.stdout.strip()):
            parser.error('Workspace must be clean and at the frozen Case commit')
    files = artifacts.inventory(workspace, source_repository=True)
    artifacts.check_profile(files)
    process = None
    if args.process_config:
        process = ProcessConfiguration.model_validate(artifacts.decode_json(artifacts.read_bytes(args.process_config)))
        identity = dict(name=args.agent_name, version=args.agent_version, adapter='process',
                        implementation_sha256=process.image.removeprefix('sha256:'))
        config_hash = digest(process.model_dump(mode='json'))
        budget = {}
    else:
        from backend.app.agent.adapters.native import NativeAdapter
        metadata = NativeAdapter().metadata()
        identity = {key: metadata[key] for key in ('name', 'version', 'adapter', 'implementation_sha256')}
        config_hash = digest(config.model_dump(mode='json'))
        budget = {'max_tool_calls': config.max_tool_calls}
    # Read-only checks; Docker never downloads an absent image here.
    for image in [args.test_image, *([process.image] if process else [])]:
        import re
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
            parser.error('Use immutable sha256 image IDs')
        inspected = docker('image', 'inspect', '--format', '{{.Id}}', image)
        if inspected.returncode or inspected.stdout.strip() != image:
            parser.error('Required local image unavailable; explicitly prepare it first')
    request = AgentRunRequest(run_id=uuid4(), case_id=case.case_id, case_version=case.case_version,
        task_description=case.user_request, repository_commit=case.repository_commit, agent=identity,
        config_sha256=config_hash, case_sha256=digest(case.model_dump(mode='json')), task_type=case.task_type,
        rule_sha256=digest(rule.model_dump(mode='json')),
        environment_sha256=environment_fingerprint(args.test_image),
        initial_snapshot_hash=artifacts.python_hash(files), editable_files=case.editable_files, budget=budget)
    run = create_run(request, repository_id=args.repository_id,
                     legacy_task_id=args.task_id, creation_key=args.creation_key)
    bundle = create_bundle(request, workspace=workspace, case=case, rule=rule, image=args.test_image,
                           process_config=process.model_dump(mode='json') if process else None)
    if process:
        enqueue_process(run.id, bundle_sha256=bundle)
    else:
        enqueue_native(run.id, bundle_sha256=bundle)
    print(f'Queued {run.id}. No model/test executed yet. Open /live/runs/{run.id}')


if __name__ == '__main__':
    main()
