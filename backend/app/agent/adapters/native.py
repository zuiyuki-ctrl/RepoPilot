"""Native 只负责执行和产物；从不把旧任务 completed 当作平台 passed。"""
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from .base import StepResult
from ...core.runtime_conditions import capture_runtime_conditions, fingerprint, require_runtime_conditions
from ...db.session import SessionLocal
from ...db.models import Repository
from ...schemas.edit import TaskFileEditRead
from ...schemas.run_config import AgentRunConfig
from ...schemas.task import TaskPlanResult, TaskPlanReviewRequest
from ...services import task_service, edit_proposal_service, plan_execution_service
from ...services.experiment_contract_service import digest
from ...services.sandbox_snapshot_service import prepare_python_test_snapshot


class NativeAdapter:
    def metadata(self):
        return {'name': 'RepoPilot Native', 'version': 'v2-day2', 'adapter': 'native',
                'implementation_sha256': fingerprint(capture_runtime_conditions())}

    def _task(self, request, state):
        task = task_service.get_task(UUID(state['task_id']))
        if task is None or str(task.repository_id) != state['repository_id']:
            raise ValueError('Native task binding changed')
        config = AgentRunConfig.model_validate(task.run_config)
        if digest(config.model_dump(mode='json')) != request.config_sha256:
            raise ValueError('Native configuration changed')
        if request.agent.implementation_sha256 != self.metadata()['implementation_sha256']:
            raise ValueError('Native runtime changed')
        require_runtime_conditions(config)
        return task

    def prepare(self, request, state):
        task = self._task(request, state)
        if task.status != 'created' or task.task_type != 'plan' or task.user_request != request.task_description:
            raise ValueError('Native requires a fresh matching plan task')
        if request.budget.token_enforcement == 'enforced' or request.budget.max_tokens is not None:
            raise ValueError('Native hard token budgets are not implemented')
        if request.budget.max_tool_calls != task.run_config.max_tool_calls:
            raise ValueError('Native tool budget must match the frozen planning configuration')
        with SessionLocal() as session:
            repository = session.get(Repository, task.repository_id)
            if repository is None or repository.commit_hash != request.repository_commit:
                raise ValueError('Native repository changed')
            workspace = Path(repository.workspace_path)
        with TemporaryDirectory(prefix='repopilot-native-') as directory:
            snapshot = prepare_python_test_snapshot(workspace, Path(directory))
            if snapshot.snapshot_hash != request.initial_snapshot_hash:
                raise ValueError('Native initial Python snapshot changed')
        return StepResult(state=state, next_stage='plan')

    def run(self, request, stage, state):
        task = self._task(request, state)
        state = dict(state)
        if stage == 'plan':
            task = task_service.run_task(task.id)
            if task is None or task.status != 'awaiting_review':
                raise ValueError('Native planning did not produce a reviewable plan')
            plan = TaskPlanResult.model_validate(task.result)
            files = sorted({file for step in plan.plan.steps for file in step.files})
            if not files or not set(files).issubset(request.editable_files):
                raise ValueError('Native plan exceeds the frozen editable scope')
            state.update(files=files, file_index=0)
            return StepResult(state=state, next_stage='review_plan', checkpoint_kind='plan',
                              checkpoint_payload=plan.model_dump(mode='json'))
        if stage == 'review_plan':
            decision = state.pop('approval')
            task_service.review_task_plan(task.id, TaskPlanReviewRequest(
                decision=decision['decision'], comment=decision['comment']))
            if decision['decision'] == 'rejected':
                return StepResult(state=state, execution_status='cancelled')
            return StepResult(state=state, next_stage='begin')
        if stage == 'begin':
            task_service.begin_plan_execution(task.id)
            return StepResult(state=state, next_stage='generate')
        if stage == 'generate':
            path = state['files'][state['file_index']]
            candidate = edit_proposal_service.generate_task_file_edit(task.id, file_path=path)
            if candidate is None or candidate.proposal.file_path != path:
                raise ValueError('Native candidate target mismatch')
            payload = candidate.model_dump(mode='json')
            state['candidate'] = payload
            return StepResult(state=state, next_stage='apply', checkpoint_kind='candidate',
                              checkpoint_payload=payload)
        if stage == 'apply':
            if state.pop('approval')['decision'] != 'approved':
                return StepResult(state=state, execution_status='cancelled')
            candidate = TaskFileEditRead.model_validate(state.pop('candidate'))
            if candidate.task_id != task.id or candidate.repository_id != task.repository_id:
                raise ValueError('Native candidate binding mismatch')
            if candidate.proposal.file_path not in request.editable_files:
                raise ValueError('Native candidate exceeds editable scope')
            result = plan_execution_service.apply_task_file_edit(task.id,
                base_file_hash=candidate.base_file_hash, proposal=candidate.proposal)
            if result is None:
                raise ValueError('Native write returned no result')
            state['file_index'] += 1
            if state['file_index'] < len(state['files']):
                return StepResult(state=state, next_stage='generate')
            return StepResult(state=state, execution_status='completed')
        raise ValueError('Unknown native stage')

    def cleanup(self):
        # 保留工作副本用于独立验收；这里没有驻留 Agent 进程或容器。
        return {'status': 'not_needed', 'workspace_retained': True}
