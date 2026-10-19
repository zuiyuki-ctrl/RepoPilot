import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from backend.app.main import app
from backend.app.services import gateway_observation_service as service
from backend.app.services.platform_resource_service import run_resources, compare_resources
from backend.app.services.experiment_contract_service import digest


def call(**updates):
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    fields = dict(id=uuid4(), run_id=uuid4(), call_id='rpgw_' + 's'*43,
        status='succeeded', transport='dashscope_fake',
        usage=dict(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        request_sha256='a'*64, result_sha256='b'*64, error_code=None,
        created_at=now, dispatched_at=now, completed_at=now+timedelta(seconds=2),
        worker_token=uuid4(), private_body='never publish')
    return NS(**(fields | updates))


def run():
    return NS(id=uuid4(), legacy_task_id=None, capabilities={}, lifecycle='finished',
              event_sequence=1, started_at=None, completed_at=None)


def ledger(calls):
    return service.project_ledger(uuid4(), NS(calls_reserved=len(calls), credential_sha256='secret'), calls)


def test_public_projection_hides_credentials_and_caller_text_and_is_hashable():
    item = call()
    data = ledger([item])
    encoded = json.dumps(data)
    assert item.call_id not in encoded
    assert 'worker_token' not in encoded and 'credential_sha256' not in encoded
    assert 'private_body' not in encoded
    assert len(digest(data)) == 64
    assert data['items'][0]['duration_ms'] == 2000
    assert data['synthetic_known_total_tokens'] == 15
    assert data['real_total_tokens'] is None and data['cost'] is None


@pytest.mark.parametrize('transport,source', [('mock','mock'), ('dashscope_fake','fake_upstream'),
                                            (None,'unverified'), ('live','unverified')])
def test_source_is_explicit_and_never_promotes_unknown_transport(transport, source):
    value = ledger([call(transport=transport)])
    assert value['items'][0]['usage_source'] == source
    assert value['items'][0]['real_usage_eligible'] is False
    assert value['synthetic_known_total_tokens'] == (15 if source != 'unverified' else 0)


@pytest.mark.parametrize('usage,status', [(None,'missing'), ({'prompt_tokens':True,'completion_tokens':0,'total_tokens':1},'invalid'),
    ({'prompt_tokens':1,'completion_tokens':1,'total_tokens':8},'invalid')])
def test_missing_and_invalid_usage_not_zero_success(usage, status):
    value = ledger([call(usage=usage, status='unknown', completed_at=None)])
    assert value['items'][0]['usage_status'] == status
    assert value['items'][0]['duration_ms'] is None
    assert value['synthetic_usage_known_calls'] == 0
    assert value['real_total_tokens'] is None


def test_unknown_result_with_known_usage_preserves_diagnostic_subtotal():
    value = ledger([call(status='unknown')])
    assert value['synthetic_known_total_tokens'] == 15
    assert value['items'][0]['status'] == 'unknown'


def test_policy_is_frozen_validated_and_remaining_quota_is_not_authorization():
    grant = NS(policy={'model':'qwen-plus','max_calls':4}, calls_reserved=2,
               revoked_at=datetime.now(timezone.utc))
    value = service.project_ledger(uuid4(), grant, [])
    assert value['policy']['model'] == 'qwen-plus'
    assert value['calls_remaining'] == 2 and value['revoked'] is True
    grant.policy['secret'] = 'must not publish'
    value = service.project_ledger(uuid4(), grant, [])
    assert value['policy'] is None and value['calls_remaining'] is None
    assert 'must not publish' not in json.dumps(value)


@pytest.mark.parametrize('calls', [[], [call()]])
def test_gateway_grant_excludes_self_report_even_with_different_id(calls):
    row = run()
    event = NS(sequence=1,event_type='PROCESS_TRACE',payload=dict(protocol_version=1,event_id='e',
        run_id=str(row.id),kind='model_call',call_id='different',input_tokens=2,output_tokens=3,total_tokens=5))
    original = run_resources(row, [event])
    assert original['tokens']['known_total_tokens'] == 5
    result = run_resources(row, [event], gateway=ledger(calls))
    assert result['excluded_reported_calls'] == 1
    assert result['tokens']['known_total_tokens'] == 0
    assert result['tokens']['total_tokens'] is None
    assert result['source'] == 'platform_gateway_ledger'
    comparison = dict(summary={'planned_pairs':1}, pairs=[dict(case_index=0,repetition=1,
        classification='both_passed',baseline={'run_id':'a'},candidate={'run_id':'b'})])
    assert compare_resources(comparison, {'a':result,'b':result})['metrics']['total_tokens']['valid_pairs'] == 0


def test_batch_queries_share_supplied_session_and_filter_run_ids():
    row = call()
    other = uuid4()
    session = MagicMock()
    session.scalars.side_effect = [[NS(run_id=row.run_id,calls_reserved=1)], [row]]
    result = service.load_ledgers(session, [row.run_id, other])
    assert session.scalars.call_count == 2
    assert result[row.run_id]['call_count'] == 1
    assert result[other]['grant_present'] is False
    for args in session.scalars.call_args_list:
        statement = args.args[0]
        assert set(next(iter(statement.compile().params.values()))) == {row.run_id, other}


def test_api_returns_unknown_for_legacy_and_distinguishes_errors():
    rid = uuid4()
    with TestClient(app) as client, patch.object(service, 'get_ledger') as read:
        read.return_value = service.project_ledger(rid, None, [])
        response = client.get(f'/api/v2/runs/{rid}/model-calls')
        assert response.status_code == 200
        assert response.json()['real_total_tokens'] is None
        read.return_value = None
        assert client.get(f'/api/v2/runs/{rid}/model-calls').status_code == 404
        read.side_effect = SQLAlchemyError('private DB information')
        response = client.get(f'/api/v2/runs/{rid}/model-calls')
        assert response.status_code == 503
        assert 'private DB information' not in response.text


def test_read_uses_readonly_repeatable_snapshot_and_missing_run_skips_queries():
    with patch.object(service, 'SessionLocal') as factory, patch.object(service, 'load_ledgers') as load:
        session = factory.return_value.__enter__.return_value
        session.get.return_value = None
        assert service.get_ledger(uuid4()) is None
        assert 'REPEATABLE READ, READ ONLY' in str(session.execute.call_args.args[0])
        load.assert_not_called()
