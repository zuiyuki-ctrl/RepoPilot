import hashlib
import os
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from backend.app.main import app
from backend.app.schemas.model_gateway import ModelPolicy, ModelCallRequest, body_bytes, forwarded_body
from backend.app.services import gateway_request_evidence as service


def body(messages=None):
    policy = ModelPolicy(model='qwen-plus', max_request_bytes=262144, max_messages=64)
    request = ModelCallRequest(call_id='test', messages=messages or [{'role':'user','content':'Please fix the bug.'}])
    return body_bytes(forwarded_body(policy, request)), policy.model_dump()


def stored(tmp_path, raw):
    run_id = uuid4()
    digest = hashlib.sha256(raw).hexdigest()
    directory = tmp_path / str(run_id) / 'gateway' / 'requests'
    directory.mkdir(parents=True)
    path = directory / f'{digest}.json'
    path.write_bytes(raw)
    return run_id, digest, path


def db_state():
    run_id, call_id = uuid4(), uuid4()
    raw, policy = body()
    call = NS(id=call_id, request_sha256=hashlib.sha256(raw).hexdigest(), dispatched_at=datetime.now(timezone.utc))
    run = NS(lifecycle='finished')
    grant = NS(policy=policy, revoked_at=datetime.now(timezone.utc), credential_sha256=None)
    session = MagicMock()
    session.scalar.return_value = call
    session.get.side_effect = [run, grant]
    return run_id, call_id, raw, session, run, grant


def test_exact_request_and_parameters_preserved_when_no_redaction():
    raw, policy = body([{'role':'system','content':'Use source evidence.'}, {'role':'user','content':'中文源码'}])
    value = service.project_request(raw, policy)
    assert value['parameters']['model'] == 'qwen-plus'
    assert value['parameters']['stream'] is False
    assert value['display_status'] == 'unchanged'
    assert [m['content'] for m in value['messages']] == ['Use source evidence.', '中文源码']
    assert value['original_bytes'] == len(raw)


def test_redacts_before_truncation_and_applies_total_budget():
    credential = 'rpgw_' + 'a'*43
    raw, policy = body([{'role':'user','content':'x'*3990 + credential + ' Bearer abc.def sk-abcdefghijk'}] +
                       [{'role':'assistant','content':'y'*5000}] * 5)
    value = service.project_request(raw, policy)
    assert value['redacted'] and value['truncated']
    assert value['display_status'] == 'redacted_and_truncated'
    assert credential[:10] not in value['messages'][0]['content']
    assert sum(m['displayed_chars'] for m in value['messages']) == 16000
    assert all(m['displayed_chars'] <= 4000 for m in value['messages'])
    assert value['messages'][-1]['content'] == '' and value['messages'][-1]['truncated']


def test_redacted_only_and_json_escaped_secret():
    credential = 'rpgw_' + 'x'*43
    raw, policy = body([{'role':'user','content':credential + '\nBearer abcd'}])
    value = service.project_request(raw, policy)
    assert value['display_status'] == 'redacted'
    assert value['messages'][0]['content'] == '[REDACTED]\n[REDACTED]'
    assert value['messages'][0]['original_chars'] > value['messages'][0]['displayed_chars']


@pytest.mark.parametrize('edit', ['model', 'extra', 'role', 'policy'])
def test_schema_and_frozen_policy_mismatch_fail_closed(edit):
    import json
    raw, policy = body()
    data = json.loads(raw)
    if edit == 'model': data['model'] = 'qwen-other'
    if edit == 'extra': data['headers'] = {'Authorization':'do not publish'}
    if edit == 'role': data['messages'][0]['role'] = 'tool'
    if edit == 'policy': policy['max_output_tokens'] = 1
    with pytest.raises(ValueError): service.project_request(body_bytes(data), policy)


def test_artifact_fixed_path_hash_and_size(tmp_path, monkeypatch):
    monkeypatch.setenv('PLATFORM_ARTIFACT_ROOT', str(tmp_path))
    raw, _ = body()
    rid, digest, path = stored(tmp_path, raw)
    assert service.read_request(rid, digest) == raw
    path.write_bytes(raw + b' ')
    with pytest.raises(ValueError): service.read_request(rid, digest)
    path.write_bytes(b'x' * (service.MAX_ARTIFACT_BYTES + 1))
    with pytest.raises(ValueError): service.read_request(rid, digest)
    with pytest.raises(ValueError): service.read_request(rid, '../outside')


def test_missing_artifact_does_not_create_directories(tmp_path, monkeypatch):
    root = tmp_path / 'absent'
    monkeypatch.setenv('PLATFORM_ARTIFACT_ROOT', str(root))
    with pytest.raises(FileNotFoundError): service.read_request(uuid4(), 'a'*64)
    assert not root.exists()


def test_hardlink_artifact_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv('PLATFORM_ARTIFACT_ROOT', str(tmp_path))
    raw, _ = body()
    rid, digest, path = stored(tmp_path, raw)
    os.link(path, tmp_path / 'duplicate')
    with pytest.raises(ValueError): service.read_request(rid, digest)


def test_reparse_parent_rejected_before_open(tmp_path, monkeypatch):
    monkeypatch.setenv('PLATFORM_ARTIFACT_ROOT', str(tmp_path))
    raw, _ = body()
    rid, digest, path = stored(tmp_path, raw)
    original = service._is_link_or_reparse_point
    with patch.object(service, '_is_link_or_reparse_point', side_effect=lambda p: True if p == path.parent else original(p)), \
         patch.object(service.artifacts, 'read_bytes') as read:
        with pytest.raises(ValueError): service.read_request(rid, digest)
        read.assert_not_called()


@pytest.mark.parametrize('lifecycle,revoked,credential', [('running',True,None), ('finished',False,None),
    ('interrupted',True,'still-bound')])
def test_active_or_unrevoked_run_never_reads_file(lifecycle, revoked, credential):
    rid, cid, raw, session, run, grant = db_state()
    run.lifecycle = lifecycle
    grant.revoked_at = datetime.now(timezone.utc) if revoked else None
    grant.credential_sha256 = credential
    with patch.object(service, 'SessionLocal') as factory, patch.object(service, 'read_request') as read:
        factory.return_value.__enter__.return_value = session
        value = service.get_request_evidence(rid, cid)
        assert value['status'] == 'withheld' and value['preview'] is None
        read.assert_not_called()


def test_request_is_bound_to_run_and_call_in_query():
    rid, cid, raw, session, _, _ = db_state()
    session.scalar.return_value = None
    with patch.object(service, 'SessionLocal') as factory, patch.object(service, 'read_request') as read:
        factory.return_value.__enter__.return_value = session
        assert service.get_request_evidence(rid, cid) is None
        params = session.scalar.call_args.args[0].compile().params
        assert set(params.values()) == {rid, cid}
        read.assert_not_called()


@pytest.mark.parametrize('failure,status', [(FileNotFoundError('private/path'),'missing'),
    (PermissionError('private/path'),'unavailable'), (ValueError('private secret'),'invalid')])
def test_artifact_failure_is_controlled(failure, status):
    rid, cid, _, session, _, _ = db_state()
    with patch.object(service, 'SessionLocal') as factory, patch.object(service, 'read_request',side_effect=failure):
        factory.return_value.__enter__.return_value = session
        result = service.get_request_evidence(rid, cid)
        assert result['status'] == status and result['preview'] is None
        assert 'private' not in str(result) and result['hash_verified'] is False


def test_completed_evidence_real_file_and_api(tmp_path, monkeypatch):
    monkeypatch.setenv('PLATFORM_ARTIFACT_ROOT', str(tmp_path))
    _, cid, raw, session, _, _ = db_state()
    rid, _, _ = stored(tmp_path, raw)
    with patch.object(service, 'SessionLocal') as factory, TestClient(app) as client:
        factory.return_value.__enter__.return_value = session
        response = client.get(f'/api/v2/runs/{rid}/model-calls/{cid}/request')
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        value = response.json()
        assert value['status'] == 'recorded' and value['hash_verified'] is True
        assert value['preview']['messages'][0]['content'] == 'Please fix the bug.'


def test_api_missing_and_db_error_do_not_disclose_details():
    with TestClient(app) as client, patch.object(service,'get_request_evidence') as read:
        url = f'/api/v2/runs/{uuid4()}/model-calls/{uuid4()}/request'
        read.return_value = None
        assert client.get(url).status_code == 404
        read.side_effect = SQLAlchemyError('private database')
        response = client.get(url)
        assert response.status_code == 503 and 'private database' not in response.text
