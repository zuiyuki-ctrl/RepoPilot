"""Offline status projection and route tests. Database is mocked."""
import unittest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from backend.app.services import worker_status_service as service
from backend.app.api.routes.platform_catalog import router


class WorkerStatusTests(unittest.TestCase):
    def test_presence_query_is_read_only_and_database_scoped(self):
        for present in (True, False):
            engine = MagicMock()
            connection = engine.connect.return_value.__enter__.return_value
            connection.scalar.return_value = present
            with patch.object(service, 'engine', engine):
                self.assertEqual(service.get_worker_status(), dict(
                    connection_present=present, basis='database_advisory_lock'))
            statement, params = connection.scalar.call_args.args
            self.assertIn('current_database()', str(statement))
            self.assertIn('objsubid = 1', str(statement))
            self.assertNotIn('pg_try_advisory_lock', str(statement))
            self.assertEqual(params, {'high': 0, 'low': 714202602})

    def test_route_precedes_generic_catalog_and_errors_are_not_offline(self):
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            for present in (True, False):
                with patch.object(service, 'get_worker_status', return_value=dict(
                        connection_present=present, basis='database_advisory_lock')):
                    response = client.get('/api/v2/worker-status')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['connection_present'], present)
            with patch.object(service, 'get_worker_status', side_effect=SQLAlchemyError('offline')):
                self.assertEqual(client.get('/api/v2/worker-status').status_code, 503)
