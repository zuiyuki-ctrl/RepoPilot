"""Offline draft workflow: models, DB and Docker are mocked; no paid calls or Agent Runs."""
import importlib.util
import json
from contextlib import nullcontext
from io import StringIO
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import uuid4
from unittest.mock import MagicMock, patch
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from backend.app.schemas.case_draft import DraftSelection, DraftText, DraftCreate, DraftEdit, DraftConfirm, DraftRevision
from backend.app.db.models.case_draft import CaseDraft
from backend.app.services import case_draft_source as source, case_draft_service as store, case_draft_worker as worker
from backend.app.services import platform_test_collector as collector, platform_catalog_service as catalog
from backend.app.services import catalog_validation_service as validation
from backend.app.services.test_report_parser import parse_test_report
from backend.app.services.run_lifecycle import RunConflictError
from backend.app.api.routes.case_drafts import router

IMAGE = 'sha256:' + 'a' * 64
FILES = {'logic.py': b'def value(): return 0\n',
         'tests/test_logic.py': b'from logic import value\ndef test_value(): assert value() == 1\n',
         'other.py': b'# must never be sent to model\n'}
TEST = dict(classname='tests.test_logic', name='test_value')


def selection(**updates):
    return DraftSelection.model_validate(dict(repository_id=uuid4(), repository_commit='a'*40,
        source_files=['logic.py'], protected_test_files=['tests/test_logic.py'], test_image=IMAGE,
        background='数值返回错误', acceptance=dict(version='v1', required_tests=[TEST],
        baseline_failure_tests=[TEST]), **updates))


def generated(**updates):
    return DraftText.model_validate({'title':'修正数值行为', 'user_request':'当前数值返回异常，预期满足验收测试；保持测试不变。',
                                    'editable_files':['logic.py'], **updates})


def xml(mode='failed'):
    tag = {'failed':'<failure/>', 'passed':'', 'error':'<error/>', 'skipped':'<skipped/>'}[mode]
    return (f'<testsuite tests="1" failures="{int(mode=="failed")}" errors="{int(mode=="error")}" skipped="{int(mode=="skipped")}">'
        f'<testcase classname="tests.test_logic" name="test_value">{tag}</testcase></testsuite>').encode()


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    # Any missed mock fails immediately, rather than touching configured credentials, DB or Docker.
    def forbidden(*args, **kwargs):
        raise AssertionError('Unexpected external I/O in offline draft test')
    monkeypatch.setattr(source, 'request_tool_turn', forbidden)
    monkeypatch.setattr(collector, 'run_container', forbidden)
    monkeypatch.setattr(source, 'SessionLocal', MagicMock(side_effect=forbidden))
    monkeypatch.setattr(store, 'SessionLocal', MagicMock(side_effect=forbidden))
    monkeypatch.setattr(worker, 'remove_owned', MagicMock())
    monkeypatch.setattr(source, 'model_identity', lambda: dict(model='mock-model', destination='mock.invalid', configuration_sha256='b'*64))


def claim_for(chosen):
    preview = source.preview(chosen, files=FILES)
    preview['authorization'] = dict(allow_model=True, allow_baseline_tests=True)
    return dict(id=uuid4(), token=uuid4(), selection=chosen.model_dump(mode='json'),
                preview={k:v for k,v in preview.items() if k != 'contents'})


def row_for(claim, **updates):
    return NS(id=claim['id'], status='validating', revision=1, active_token=claim['token'],
        selection=claim['selection'], preview=claim['preview'], text=None, baseline=None, error=None,
        observation=None, confirmed_benchmark_id=None, confirmation=None, created_at=None, completed_at=None,
        **updates)


def db_row(monkeypatch, row):
    session = MagicMock()
    session.get.return_value = row
    session.scalar.return_value = None
    monkeypatch.setattr(store.SessionLocal, 'begin', lambda: nullcontext(session))
    return session


def test_generate_edit_confirm_reuses_catalog_without_a_run(monkeypatch, tmp_path):
    chosen = selection(); claim = claim_for(chosen); row = row_for(claim)
    db_row(monkeypatch, row)
    monkeypatch.setattr(source, 'repository_files', lambda *a: (chosen.repository_commit, FILES))
    monkeypatch.setattr(worker, 'require_image', lambda _: None)
    monkeypatch.setattr(worker.artifacts, 'run_directory', lambda _: tmp_path / 'draft')
    def run(owner, phase, **kwargs):
        assert owner == claim['id'] and phase == 'baseline'
        assert kwargs['argv'][:3] == ['python','-I','-c']
        assert kwargs['mounts'][0][2] and kwargs['mounts'][1][2]
        assert kwargs['timeout_seconds'] == 120
        (kwargs['mounts'][2][0] / 'junit.xml').write_bytes(xml())
        return dict(exit_code=1, timed_out=False, stdout='', stderr='')
    monkeypatch.setattr(collector, 'run_container', run)
    model = MagicMock(return_value={'content':json.dumps(generated().model_dump())})
    monkeypatch.setattr(source, 'request_tool_turn', model)
    with patch.object(catalog,'register_in_session') as register, patch.object(catalog,'queue_validation_in_session') as queue:
        worker.execute_draft(claim, allow_model=True)
        assert row.status == 'ready' and row.baseline['passed'] and row.active_token is None
        register.assert_not_called(); queue.assert_not_called()
        sent = json.loads(model.call_args.args[0][1]['content'])
        assert set(sent['files']) == set(chosen.source_files + chosen.protected_test_files)
        assert 'other.py' not in sent['files'] and model.call_args.kwargs['allow_tools'] is False
        store.edit_draft(row.id, DraftEdit(revision=row.revision, text=generated(title='人工修订题名')))
        register.assert_not_called()
        register.return_value = dict(id=uuid4())
        req = DraftConfirm(revision=row.revision, suite_name='generated', suite_version='v1', case_id='value', case_version='v1')
        saved = store.confirm_draft(row.id, req)
        assert saved['status'] == 'confirmed' and row.confirmed_benchmark_id == register.return_value['id']
        registration = register.call_args.args[2]
        assert registration.cases[0].case.repository_commit == chosen.repository_commit
        assert registration.cases[0].acceptance == chosen.acceptance
        assert registration.cases[0].case.user_request.startswith('人工修订题名\n\n')
        queue.assert_called_once()
        # Retry a lost response returns the same result without duplicating the registration.
        store.confirm_draft(row.id, req)
        register.assert_called_once()


@pytest.mark.parametrize('change', [
    {'repository_commit':'f'*40}, {'command':'pytest'}, {'editable_files':['../secret.py']},
    {'editable_files':['missing.py']}, {'editable_files':['tests/test_logic.py']},
    {'editable_files':['other.py']}, {'editable_files':['C:\\logic.py']},
    {'editable_files':['logic.py','logic.py']}, {'title':' '}, {'user_request':'```diff\npatch\n```'}])
def test_model_illegal_fields_paths_and_patch_rejected(monkeypatch, change):
    raw = {**generated().model_dump(), **change}
    monkeypatch.setattr(source, 'request_tool_turn', lambda *a, **k: {'content':json.dumps(raw)})
    with pytest.raises(source.DraftInputError):
        source.generate_text(selection(), {}, worker.ModelObservation())


@pytest.mark.parametrize('mode,exit_code,reason', [
    ('passed',0,'baseline_all_passed'), ('error',1,'tests_errored_or_skipped'),
    ('skipped',0,'tests_errored_or_skipped'), ('failed',2,'test_process_failed')])
def test_baseline_not_usable(mode, exit_code, reason):
    result = collector.assess_baseline(parse_test_report(xml(mode)),exit_code=exit_code,timed_out=False,
        rule=selection().acceptance,task_type='bug_fix',exact_failures=True)
    assert not result['passed'] and result['reason'] == reason


def test_expected_failure_mismatch_and_missing_and_timeout():
    rule = selection().acceptance
    report = parse_test_report(xml().replace(b'test_value', b'test_unexpected'))
    result = collector.assess_baseline(report,exit_code=1,timed_out=False,rule=rule,task_type='bug_fix',exact_failures=True)
    assert not result['passed'] and result['missing'] == [TEST]
    extra = xml().replace(b'tests="1" failures="1"',b'tests="2" failures="2"').replace(b'</testsuite>',
        b'<testcase classname="tests.test_logic" name="test_extra"><failure/></testcase></testsuite>')
    result = collector.assess_baseline(parse_test_report(extra),exit_code=1,timed_out=False,rule=rule,task_type='bug_fix',exact_failures=True)
    assert result['reason'] == 'baseline_failures_mismatch' and result['unexpected'][0]['name'] == 'test_extra'
    for report, timeout, reason in [(None,False,'test_report_missing_or_invalid'),(parse_test_report(xml()),True,'baseline_timed_out')]:
        assert collector.assess_baseline(report,exit_code=1,timed_out=timeout,rule=rule,task_type='bug_fix',exact_failures=True)['reason'] == reason


def test_worker_failed_baseline_skips_model_and_retains_reason(monkeypatch):
    chosen = selection(); claim = claim_for(chosen); row = row_for(claim); db_row(monkeypatch,row)
    monkeypatch.setattr(source,'repository_files',lambda *a:(chosen.repository_commit,FILES))
    monkeypatch.setattr(worker,'check_baseline',lambda *a:dict(passed=False,reason='baseline_all_passed'))
    model = MagicMock(); monkeypatch.setattr(source,'generate_text',model)
    worker.execute_draft(claim,allow_model=True)
    model.assert_not_called()
    assert row.status == 'failed' and row.error['reason'] == 'baseline_all_passed' and row.text is None


def test_unavailable_image_has_actionable_reason(monkeypatch):
    chosen=selection(); claim=claim_for(chosen); row=row_for(claim); db_row(monkeypatch,row)
    monkeypatch.setattr(source,'repository_files',lambda *a:(chosen.repository_commit,FILES))
    monkeypatch.setattr(worker,'require_image',MagicMock(side_effect=ValueError('local_image_unavailable')))
    worker.execute_draft(claim,allow_model=True)
    assert row.status=='failed' and row.error['reason']=='local_image_unavailable'
    assert '完整 Id' in row.error['message']


def test_cleanup_failure_keeps_ownership_fence(monkeypatch):
    chosen = selection(); claim = claim_for(chosen); row = row_for(claim); db_row(monkeypatch,row)
    monkeypatch.setattr(source,'repository_files',lambda *a:(chosen.repository_commit,FILES))
    monkeypatch.setattr(worker,'check_baseline',lambda *a:dict(passed=False,reason='baseline_all_passed'))
    monkeypatch.setattr(worker,'remove_owned',MagicMock(side_effect=RuntimeError('unconfirmed')))
    worker.execute_draft(claim,allow_model=True)
    assert row.status == 'interrupted' and row.active_token == claim['token']


def test_no_worker_model_permission_or_changed_preview_never_calls_model(monkeypatch):
    for allow in (False, True):
        chosen = selection(); claim = claim_for(chosen); row = row_for(claim); db_row(monkeypatch,row)
        monkeypatch.setattr(source,'repository_files',lambda *a:(chosen.repository_commit,{**FILES,'logic.py':b'changed'}))
        probe = MagicMock(); monkeypatch.setattr(worker,'check_baseline',probe)
        worker.execute_draft(claim,allow_model=allow)
        probe.assert_not_called()
        assert row.status == 'failed'
    assert store.claim_draft(allow_model=False) is None


def test_missing_persisted_consent_and_model_failure_cannot_become_ready(monkeypatch):
    chosen=selection(); claim=claim_for(chosen); row=row_for(claim); db_row(monkeypatch,row)
    claim['preview'].pop('authorization')
    probe=MagicMock(); monkeypatch.setattr(worker,'check_baseline',probe)
    worker.execute_draft(claim,allow_model=True)
    assert row.status == 'failed'
    probe.assert_not_called()
    claim=claim_for(chosen); row=row_for(claim); db_row(monkeypatch,row)
    monkeypatch.setattr(source,'repository_files',lambda *a:(chosen.repository_commit,FILES))
    monkeypatch.setattr(worker,'check_baseline',lambda *a:dict(passed=True,reason='baseline_matches'))
    monkeypatch.setattr(source,'request_tool_turn',MagicMock(side_effect=RuntimeError('secret network response')))
    worker.execute_draft(claim,allow_model=True)
    assert row.status == 'failed' and row.text is None
    assert 'secret network response' not in str(row.error)


def test_create_persists_authorized_job_only(monkeypatch):
    chosen=selection(); checked=source.preview(chosen,files=FILES)
    req=DraftCreate(selection=chosen,preview_sha256=checked['preview_sha256'],request_key=uuid4(),allow_model=True,allow_baseline_tests=True)
    session=MagicMock(); session.scalar.return_value=None
    factory=MagicMock(return_value=nullcontext(session)); factory.begin.return_value=nullcontext(session)
    monkeypatch.setattr(store,'SessionLocal',factory)
    monkeypatch.setattr(source,'preview',lambda *a:checked)
    def flush():
        row=session.add.call_args.args[0]
        row.id, row.status, row.revision = uuid4(),'queued',0
    session.flush.side_effect=flush
    with patch.object(catalog,'register_in_session') as register:
        result=store.create_draft(req)
        assert result['status']=='queued' and result['confirmed_benchmark_id'] is None
        register.assert_not_called()
    job=session.add.call_args.args[0]
    assert isinstance(job,CaseDraft) and job.preview['authorization']==dict(allow_model=True,allow_baseline_tests=True)
    assert 'contents' not in job.preview


@pytest.mark.parametrize('status', ['queued','validating','generating','failed','interrupted','discarded'])
def test_unconfirmed_or_invalid_cannot_register(monkeypatch,status):
    row = row_for(claim_for(selection())); row.status=status; row.active_token=None
    db_row(monkeypatch,row)
    with patch.object(catalog,'register_in_session') as register:
        with pytest.raises(RunConflictError):
            store.confirm_draft(row.id,DraftConfirm(revision=row.revision,suite_name='x',suite_version='v1',case_id='x',case_version='v1'))
        register.assert_not_called()


def test_ready_without_baseline_and_stale_edit_are_rejected(monkeypatch):
    row = row_for(claim_for(selection())); row.status='ready'; row.active_token=None; row.text=generated().model_dump()
    db_row(monkeypatch,row)
    with pytest.raises(RunConflictError):
        store.confirm_draft(row.id,DraftConfirm(revision=row.revision,suite_name='x',suite_version='v1',case_id='x',case_version='v1'))
    with pytest.raises(RunConflictError):
        store.edit_draft(row.id,DraftEdit(revision=row.revision+1,text=generated()))
    with pytest.raises(ValueError):
        store.edit_draft(row.id,DraftEdit(revision=row.revision,text=generated(editable_files=['tests/test_logic.py'])))
    store.discard_draft(row.id,DraftRevision(revision=row.revision))
    assert row.status == 'discarded' and row.confirmed_benchmark_id is None


def test_api_requires_explicit_authorization_and_no_client_ready_flag(monkeypatch):
    app=FastAPI(); app.include_router(router)
    body=dict(selection=selection().model_dump(mode='json'),preview_sha256='a'*64,request_key=str(uuid4()),allow_model=True,allow_baseline_tests=True)
    create=MagicMock(return_value={'id':str(uuid4()),'status':'queued'})
    monkeypatch.setattr(store,'create_draft',create)
    with TestClient(app) as client:
        for change in ({'allow_model':False},{'allow_baseline_tests':False},{'allow_model':'true'},{'status':'ready'}):
            assert client.post('/api/v2/case-drafts',json={**body,**change}).status_code == 422
        create.assert_not_called()
        assert client.post('/api/v2/case-drafts',json=body).status_code == 202


def test_preview_is_local_bounded_and_only_selected_contents():
    chosen=selection(); preview=source.preview(chosen,files=FILES)
    assert set(preview['contents']) == {'logic.py','tests/test_logic.py'}
    assert len(preview['preview_sha256']) == 64
    for files in ({'logic.py':b'x'}, {**FILES,'logic.py':b'x'*120001}):
        with pytest.raises(source.DraftInputError): source.preview(chosen,files=files)


def test_create_is_idempotent_and_preview_hash_is_required(monkeypatch):
    chosen=selection(); preview=source.preview(chosen,files=FILES)
    request=DraftCreate(selection=chosen,preview_sha256=preview['preview_sha256'],request_key=uuid4(),allow_model=True,allow_baseline_tests=True)
    row=row_for(claim_for(chosen)); row.request_sha256=store.digest(request.model_dump(mode='json',exclude={'request_key'}))
    session=MagicMock(); session.scalar.return_value=row
    monkeypatch.setattr(store,'SessionLocal',lambda:nullcontext(session))
    assert store.create_draft(request)['id'] == row.id
    row.request_sha256='different'
    with pytest.raises(RunConflictError): store.create_draft(request)
    session.scalar.return_value=None
    monkeypatch.setattr(source,'preview',lambda *a:{**preview,'preview_sha256':'0'*64})
    with pytest.raises(RunConflictError): store.create_draft(request)


def test_catalog_validation_rejects_stale_draft_baseline(monkeypatch):
    chosen=selection(); item=chosen.binding(generated())
    descriptor=dict(name='draft',version='v1',cases=[item.model_dump(mode='json')])
    session=MagicMock(); session.get.return_value=NS(workspace_path='unused',commit_hash=chosen.repository_commit)
    monkeypatch.setattr(validation,'SessionLocal',lambda:nullcontext(session))
    monkeypatch.setattr(validation.subprocess,'run',MagicMock(side_effect=[NS(returncode=0,stdout=chosen.repository_commit),NS(returncode=0,stdout='')]))
    monkeypatch.setattr(validation.artifacts,'inventory',lambda *a,**k:FILES)
    with pytest.raises(ValueError,match='draft_baseline_evidence_changed'):
        validation.validate_benchmark(dict(id=uuid4(),descriptor=descriptor,
            draft_preview=dict(snapshot_sha256='0'*64,runner_sha256=collector.runner_fingerprint()),
            draft_baseline=dict(passed=True,image=IMAGE)))


def test_migration_offline_and_worker_fence():
    spec=importlib.util.spec_from_file_location('draft_migration',Path('backend/migrations/versions/d1113a01b001_add_case_drafts.py'))
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    output=StringIO(); context=MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})
    with Operations.context(context): module.upgrade(); module.downgrade()
    assert 'CREATE TABLE case_drafts' in output.getvalue() and 'RAISE EXCEPTION' in output.getvalue()
    session=MagicMock(); session.scalar.return_value=uuid4()
    with pytest.raises(RunConflictError): catalog.assert_no_catalog_writer(session)
    assert 'case_drafts' in str(session.scalar.call_args.args[0])


def test_repository_preview_rejects_dirty_or_wrong_commit_and_ignored_files(monkeypatch):
    chosen=selection()
    session=MagicMock(); session.get.return_value=NS(workspace_path='registered',commit_hash=chosen.repository_commit,test_profile='python-basic')
    monkeypatch.setattr(source,'SessionLocal',lambda:nullcontext(session))
    monkeypatch.setattr(source.artifacts,'inventory',lambda *a,**k:FILES)
    with pytest.raises(source.DraftInputError,match='提交必须'):
        source.repository_files(chosen.repository_id,'f'*40)
    monkeypatch.setattr(source.subprocess,'run',MagicMock(return_value=NS(returncode=0,stdout='f'*40)))
    with pytest.raises(source.DraftInputError,match='干净状态'):
        source.repository_files(chosen.repository_id,chosen.repository_commit)
    monkeypatch.setattr(source.subprocess,'run',MagicMock(side_effect=[
        NS(returncode=0,stdout=chosen.repository_commit),NS(returncode=0,stdout=''),
        NS(returncode=0,stdout='logic.py\0tests/test_logic.py\0')]))
    with pytest.raises(source.DraftInputError,match='忽略文件'):
        source.repository_files(chosen.repository_id,chosen.repository_commit)


def test_persistent_worker_dispatches_drafts_only_with_opt_in(monkeypatch):
    from backend.app.services import platform_worker, platform_experiment_service, experiment_preparation
    engine=MagicMock()
    engine.connect.return_value.execution_options.return_value.__enter__.return_value.scalar.return_value=True
    monkeypatch.setattr(platform_worker,'engine',engine)
    monkeypatch.setattr(platform_worker.store,'claim_next',lambda **k:None)
    monkeypatch.setattr(catalog,'claim_validation',lambda:None)
    monkeypatch.setattr(platform_experiment_service,'claim_preparation',lambda **k:None)
    claim=claim_for(selection())
    monkeypatch.setattr(store,'claim_draft',lambda **k:claim if k['allow_model'] else None)
    execute=MagicMock(); monkeypatch.setattr(worker,'execute_draft',execute)
    platform_worker.run_worker(once=True,allow_model=False)
    execute.assert_not_called()
    platform_worker.run_worker(once=True,allow_model=True)
    execute.assert_called_once_with(claim,allow_model=True)


def test_recovery_checks_token_and_does_not_replay(monkeypatch):
    from backend.app.services import platform_container
    claim=claim_for(selection()); row=row_for(claim); row.status='interrupted'
    session=MagicMock(); session.get.return_value=row
    factory=MagicMock(return_value=nullcontext(session)); factory.begin.return_value=nullcontext(session)
    monkeypatch.setattr(store,'SessionLocal',factory)
    remove=MagicMock(); monkeypatch.setattr(platform_container,'remove_owned',remove)
    with pytest.raises(RunConflictError): store.recover_draft(row.id,uuid4())
    remove.assert_not_called()
    store.recover_draft(row.id,claim['token'])
    remove.assert_called_once_with(row.id,'baseline')
    assert row.status=='failed' and row.active_token is None and row.confirmed_benchmark_id is None
