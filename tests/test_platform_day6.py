"""Trace read boundary tests; no database, workspace, Docker or model calls."""
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from uuid import UUID
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services import platform_trace_service as trace
from backend.app.services.run_observation_service import summarize_observation


RID = UUID(int=6)


def event(payload, sequence=12, event_type='MODEL_CALL_STARTED', source='adapter'):
    return NS(id=UUID(int=sequence), run_id=RID, sequence=sequence,
              event_type=event_type, source=source, payload=payload,
              created_at=datetime(2026, 10, 16, tzinfo=timezone.utc))


class TraceTests(unittest.TestCase):
    def test_native_sequence_and_call_reference_preserved_without_raw_secrets(self):
        row = trace.trace_event(event({'legacy_task_id': str(RID), 'legacy_sequence': 3,
            'node_name': 'model', 'native': {'call_id': 'call-a', 'sequence': 3,
                'headers': {'Authorization': 'secret'}, 'messages': ['private'],
                'tool_context': [{'tool_call_id': 'tool-a', 'tool_message_index': 0,
                                  'content_sha256': 'a'*64, 'content_chars': 40, 'content': 'private'}]}}))
        self.assertEqual((row['sequence'], row['legacy_sequence']), (12, 3))
        self.assertEqual(row['details']['tool_context'][0]['tool_call_id'], 'tool-a')
        self.assertNotIn('private', str(row))
        self.assertNotIn('secret', str(row))
        self.assertNotIn('sequence', row['details'])

    def test_query_and_context_retained_as_distinct_events(self):
        query = trace.trace_event(event({'query': '哪里校验路径', 'hits': [
            {'file_path': 'app.py', 'rank': 1, 'content_sha256': 'a'*64}]}, event_type='RETRIEVAL_COMPLETED'))
        context = trace.trace_event(event({'disposition': 'discarded', 'sources': [],
                                         'content_sha256': 'b'*64}, event_type='TOOL_CONTEXT_PREPARED'))
        self.assertEqual(query['details']['query'], '哪里校验路径')
        self.assertEqual(context['details']['sources'], [])
        self.assertEqual(context['details']['disposition'], 'discarded')
        self.assertNotIn('model_calls', query)

    def test_usage_missing_is_not_zero_or_complete(self):
        row = trace.trace_event(event({'kind': 'model_call', 'call_id': 'a',
                                      'input_tokens': 12, 'output_tokens': None}, source='agent_reported'))
        self.assertIsNone(row['details']['output_tokens'])
        self.assertNotIn('total_tokens', row['details'])
        self.assertEqual(row['source'], 'agent_reported')
        self.assertEqual(summarize_observation({}).level, 'unknown')

    def test_nested_unknown_keys_are_not_published(self):
        row = trace.trace_event(event({'model_observation': {'call_id': 'a',
            'request_parameters': {'secret': 'hidden'}, 'usage': {'total_tokens': 4, 'secret': 'hidden'}}}))
        self.assertEqual(row['details']['model_observation']['usage'], {'total_tokens': 4})
        self.assertNotIn('hidden', str(row))

    def test_oversized_fields_are_bounded_and_marked(self):
        row = trace.trace_event(event({'query': 'x'*3000, 'hits': [{'file_path': 'y'*3000}]*100}))
        self.assertTrue(row['truncated'])
        self.assertEqual(len(row['details']['query']), 2000)
        self.assertEqual(len(row['details']['hits']), 50)
        self.assertLess(len(str(row)), 26000)

    def test_invalid_and_unknown_payload_remain_honest(self):
        self.assertEqual(trace.trace_event(event(['bad']))['detail_status'], 'invalid')
        self.assertEqual(trace.trace_event(event({'unknown': 'hidden'}))['detail_status'], 'metadata_only')
        self.assertEqual(trace.trace_event(event({'hits': 'bad'}))['detail_status'], 'invalid')

    def test_page_keeps_snapshot_boundary_and_does_not_read_artifacts(self):
        with patch.object(trace, 'SessionLocal') as factory, patch.object(trace.repo, 'get_run', return_value=NS(event_sequence=100)), \
                patch.object(trace.repo, 'list_events', return_value=[event({}, 12)]) as query:
            factory.return_value.__enter__.return_value = MagicMock()
            page = trace.list_trace(RID, after_sequence=10, limit=2, through_sequence=20)
            self.assertEqual(page['through_sequence'], 20)
            self.assertEqual(page['next_after_sequence'], 12)
            self.assertTrue(page['has_more'])
            self.assertEqual(query.call_args.kwargs['through_sequence'], 20)

    def test_empty_page_terminates_and_missing_run_distinct(self):
        with patch.object(trace, 'SessionLocal'), patch.object(trace.repo, 'get_run', return_value=NS(event_sequence=0)), \
                patch.object(trace.repo, 'list_events', return_value=[]):
            self.assertFalse(trace.list_trace(RID)['has_more'])
        with patch.object(trace, 'SessionLocal'), patch.object(trace.repo, 'get_run', return_value=None):
            self.assertIsNone(trace.list_trace(RID))

    def test_route_validation_and_not_found(self):
        with TestClient(app) as client, patch.object(trace, 'list_trace', return_value=None) as query:
            url = f'/api/v2/runs/{RID}/trace'
            self.assertEqual(client.get(url+'?after_sequence=5&through_sequence=2').status_code, 422)
            self.assertEqual(client.get(url+'?limit=101').status_code, 422)
            query.assert_not_called()
            self.assertEqual(client.get(url).status_code, 404)


if __name__ == '__main__':
    unittest.main()
