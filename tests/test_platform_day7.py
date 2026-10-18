import json
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services.platform_delivery_service import inspect_report
from backend.app.services.experiment_contract_service import digest


def report():
    manifest={'draft':{'name':'fixture'}}
    comparison={'experiment_id':str(uuid4()),'manifest_sha256':digest(manifest),'decision':{'status':'not_assessed'}}
    comparison['comparison_sha256']=digest(comparison)
    data=dict(schema_version=1,report_type='experiment_comparison_snapshot',manifest=manifest,
        manifest_sha256=digest(manifest),experiment_id=comparison['experiment_id'],comparison=comparison,
        reviews=[{'comparison_sha256':comparison['comparison_sha256'],'snapshot':deepcopy(comparison)}])
    data['report_sha256']=digest(data)
    return data


def encode(data):return json.dumps(data,ensure_ascii=False).encode()


def rehash(data):data['report_sha256']=digest({k:v for k,v in data.items() if k!='report_sha256'})


class DeliveryTests(TestCase):
    def test_report_round_trip_without_db_or_recomputation(self):
        data=report();result=inspect_report(encode(data))
        self.assertEqual(result['report'],data)
        self.assertEqual(result['source'],'uploaded_report_only')

    def test_outer_hash_tamper_rejected(self):
        data=report();data['manifest']['draft']['name']='changed'
        with self.assertRaises(ValueError):inspect_report(encode(data))

    def test_inner_hash_or_identity_tamper_rejected_even_if_outer_rehashed(self):
        for field in ('manifest','comparison','identity','review'):
            data=report()
            if field=='manifest':data['manifest']['draft']['name']='changed'
            if field=='comparison':data['comparison']['decision']['status']='passed'
            if field=='identity':data['experiment_id']=str(uuid4())
            if field=='review':data['reviews'][0]['snapshot']['decision']['status']='passed'
            rehash(data)
            with self.subTest(field=field),self.assertRaises(ValueError):inspect_report(encode(data))

    def test_duplicate_nonfinite_depth_and_bad_shape_rejected(self):
        for raw in (b'{"schema_version":1,"schema_version":1}',b'{"n":NaN}',b'{"n":1e999}',
                    b'['*45+b'0'+b']'*45,b'[]',b'not-json'):
            with self.subTest(raw=raw[:30]),self.assertRaises(ValueError):inspect_report(raw)

    def test_unknown_version_rejected(self):
        data=report();data['schema_version']=2;rehash(data)
        with self.assertRaises(ValueError):inspect_report(encode(data))

    def test_inspection_http_and_stream_limit(self):
        with TestClient(app) as client:
            self.assertEqual(client.post('/api/v2/reports/inspect',content=encode(report())).status_code,200)
            self.assertEqual(client.post('/api/v2/reports/inspect',content=b'{}').status_code,422)
            with patch('backend.app.api.routes.platform_delivery.MAX_REPORT_BYTES',10):
                self.assertEqual(client.post('/api/v2/reports/inspect',content=b'x'*11).status_code,413)

    def test_dashboard_route_returns_live_counts(self):
        with TestClient(app) as client,patch('backend.app.api.routes.platform_delivery.dashboard',return_value={
                'source':'live_database_only','execution':{'completed':2},'evaluation':{'passed':1,'not_passed':1}}):
            response=client.get('/api/v2/dashboard')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['evaluation']['passed'],1)
