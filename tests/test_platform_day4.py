"""Catalog boundary tests; database, Docker and model execution are mocked."""
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.app.schemas.platform_catalog import AgentRegistration, BenchmarkRegistration
from backend.app.services import platform_catalog_service as catalog, catalog_validation_service as validation
from backend.app.services.run_lifecycle import RunConflictError
from backend.app.api.routes.platform_catalog import router
from backend.app.services.experiment_contract_service import digest

IMAGE = 'sha256:' + 'a'*64


def registration(**updates):
    return AgentRegistration.model_validate(dict(name='fixture', version='v1', adapter='process',
        process=dict(image=IMAGE, argv=['python', '/agent/demo.py']), **updates))


def claim():
    data = registration().model_dump(mode='json')
    return dict(id=uuid4(), token=uuid4(), kind='agents', descriptor=data, content_sha256=digest(data))


class CatalogTests(TestCase):
    def test_unknown_fields_and_adapter_mismatch_rejected(self):
        for extra in ({'ready':True}, {'native':{}}, {'declared_capabilities':['execution','execution']}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                registration(**extra)

    def test_duplicate_case_rejected(self):
        case = json.loads(Path('evals/experiments/cases/task-list-v1.json').read_text(encoding='utf-8'))
        rule = json.loads(Path('evals/experiments/definitions/task-list-pipeline-v1.json').read_text(encoding='utf-8'))['acceptance']
        item = dict(repository_id=str(uuid4()), case=case, acceptance=rule, test_image=IMAGE)
        with self.assertRaises(ValidationError):
            BenchmarkRegistration(name='suite', version='v1', cases=[item, item])

    def test_version_content_conflict(self):
        session = MagicMock(); session.scalar.return_value = NS(content_sha256='b'*64)
        with patch.object(catalog.SessionLocal,'begin',return_value=nullcontext(session)):
            with self.assertRaises(RunConflictError): catalog.register('agents',registration())

    def test_request_key_cannot_cross_owner(self):
        session = MagicMock(); session.get.return_value = NS()
        session.scalar.return_value = NS(agent_version_id=uuid4())
        with patch.object(catalog.SessionLocal,'begin',return_value=nullcontext(session)):
            with self.assertRaises(RunConflictError): catalog.queue_validation('agents',uuid4(),uuid4())

    def test_active_validation_blocks_claim(self):
        session = MagicMock(); session.scalar.return_value = uuid4()
        with patch.object(catalog.SessionLocal,'begin',return_value=nullcontext(session)):
            with self.assertRaises(RunConflictError): catalog.claim_validation()

    def test_cleanup_failure_retains_token(self):
        c = claim(); job = NS(id=c['id'],active_token=c['token'],status='running',agent_version_id=uuid4(),benchmark_version_id=None)
        owner = NS(); session = MagicMock(); session.get.side_effect = [job,owner]
        with patch.object(catalog.SessionLocal,'begin',return_value=nullcontext(session)):
            catalog.settle_validation(c, {'passed':True}, cleanup_confirmed=False)
        self.assertEqual(job.active_token,c['token']); self.assertEqual(job.status,'interrupted')
        self.assertEqual(owner.status,'invalid')

    def test_protocol_identity_scope_timeout_and_success(self):
        for mode in ('good','wrong-id','outside','timeout'):
            with self.subTest(mode=mode), TemporaryDirectory() as temp:
                c = claim(); root = Path(temp)/str(c['id'])
                def run(*args, **kwargs):
                    req = json.loads((root/'input/request.json').read_text(encoding='utf-8'))
                    response = dict(protocol_version=1,run_id=req['run_id'],agent=req['agent'],execution_status='completed')
                    if mode == 'wrong-id': response['run_id'] = str(uuid4())
                    if mode == 'outside': (root/'workspace/outside.txt').write_text('bad')
                    (root/'output/result.json').write_text(json.dumps(response),encoding='utf-8')
                    return dict(exit_code=0,timed_out=mode=='timeout')
                with patch.object(validation,'require_image'), patch.object(validation.artifacts,'run_directory',return_value=root), patch.object(validation,'run_container',side_effect=run):
                    if mode == 'good':
                        result = validation.validate_agent(c)
                        self.assertEqual(result['validated_capabilities'],['execution'])
                        self.assertFalse(result['task_success_evaluated'])
                    else:
                        with self.assertRaises(ValueError): validation.validate_agent(c)

    def test_native_check_does_not_execute(self):
        data = AgentRegistration(name='native',version='v1',adapter='native',native={}).model_dump(mode='json')
        data['implementation_sha256'] = 'a'*64
        with patch('backend.app.agent.adapters.native.NativeAdapter') as adapter:
            adapter.return_value.metadata.return_value = {'implementation_sha256':'a'*64}
            report = validation.validate_agent({'descriptor':data})
            self.assertTrue(report['passed']); self.assertEqual(report['validated_capabilities'],[])
            adapter.return_value.run.assert_not_called()

    def test_existing_image_without_pytest_is_not_ready(self):
        case = json.loads(Path('evals/experiments/cases/task-list-v1.json').read_text(encoding='utf-8'))
        rule = json.loads(Path('evals/experiments/definitions/task-list-pipeline-v1.json').read_text(encoding='utf-8'))['acceptance']
        descriptor = dict(name='suite',version='v1',cases=[dict(repository_id=str(uuid4()),case=case,acceptance=rule,test_image=IMAGE)])
        session = MagicMock(); session.get.return_value = NS(workspace_path='unused',commit_hash=case['repository_commit'])
        files = {p:b'# fixture\n' for p in case['editable_files']+case['protected_test_files']}
        with patch.object(validation,'SessionLocal',return_value=nullcontext(session)), patch.object(validation.subprocess,'run',side_effect=[NS(returncode=0,stdout=case['repository_commit']),NS(returncode=0,stdout='')]), patch.object(validation.artifacts,'inventory',return_value=files), patch.object(validation,'require_image'), patch.object(validation,'run_container',return_value=dict(exit_code=1,timed_out=False)):
            with self.assertRaisesRegex(ValueError,'test_image_pytest_unavailable'):
                validation.validate_benchmark(dict(id=uuid4(),descriptor=descriptor))

    def test_invalid_hash_is_settled_not_executed(self):
        c=claim(); c['content_sha256']='0'*64
        with patch.object(validation,'validate_agent') as run, patch.object(validation,'remove_owned'), patch.object(catalog,'settle_validation') as settle:
            validation.execute_validation(c)
            run.assert_not_called(); self.assertFalse(settle.call_args.args[1]['passed'])

    def test_api_invalid_config_conflict_and_not_found(self):
        app=FastAPI(); app.include_router(router)
        with TestClient(app) as client:
            self.assertEqual(client.post('/api/v2/agents',json={'ready':True}).status_code,422)
            with patch.object(catalog,'register',side_effect=RunConflictError('version conflict')):
                self.assertEqual(client.post('/api/v2/agents',json=registration().model_dump(mode='json')).status_code,409)
            with patch.object(catalog,'get_validation',return_value=None):
                self.assertEqual(client.get('/api/v2/catalog-validations/'+str(uuid4())).status_code,404)
