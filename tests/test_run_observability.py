import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from uuid import UUID

import httpx

from backend.app.rag import embedding
from backend.app.core import runtime_conditions
from backend.app.core.exceptions import TaskStateConflictError
from backend.app.schemas.run_config import AgentRunConfig
from backend.app.services import experiment_conditions_service as conditions
from backend.app.services.request_observation_service import collect_request_observations
from backend.app.services import retrieval_service, tool_service


class EmbeddingObservationTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.multiple(embedding.config, DASHSCOPE_API_KEY="fixture",
            EMBEDDING_ENDPOINT="https://example.invalid/v1/embeddings", EMBEDDING_DIMENSIONS=1024))
        self.client = self.enterContext(patch.object(embedding.httpx, "Client")).return_value.__enter__.return_value
        self.client.post.return_value = httpx.Response(200, request=httpx.Request("POST", "https://example.invalid"),
            json={"data": [{"index": 0, "embedding": [0.1] * 1024}], "usage": {"prompt_tokens": 8, "total_tokens": 8}})
        self.records = []

    def test_embedding_usage_has_no_invented_output_tokens(self):
        embedding.embed_texts(["private code"], observation_sink=self.records.append)
        start, end = self.records
        self.assertEqual(start["status"], "started")
        self.assertEqual(start["observation"]["operation_status"], "pending")
        self.assertEqual(end["observation"]["usage_status"], "complete")
        self.assertIsNone(end["observation"]["usage"]["output_tokens"])
        self.assertEqual(end["observation"]["usage"]["input_tokens"], 8)
        self.assertEqual(end["observation"]["request_parameters"]["dimensions"], 1024)
        self.assertNotIn("private code", str(self.records))
        self.assertEqual(start["observation"]["call_id"], end["observation"]["call_id"])

    def test_empty_input_does_not_emit_or_request(self):
        self.assertEqual(embedding.embed_texts([], observation_sink=self.records.append), [])
        self.assertEqual(self.records, [])
        self.client.post.assert_not_called()

    def test_invalid_vector_keeps_usage(self):
        self.client.post.return_value = httpx.Response(200, request=httpx.Request("POST", "https://example.invalid"),
            json={"data": [{"index": 0, "embedding": []}], "usage": {"prompt_tokens": 8, "total_tokens": 8}})
        with self.assertRaises(ValueError):
            embedding.embed_texts(["x"], observation_sink=self.records.append)
        self.assertEqual(self.records[-1]["status"], "failed")
        self.assertEqual(self.records[-1]["observation"]["usage"]["total_tokens"], 8)

    def test_persistence_failure_does_not_repeat_embedding(self):
        sink = Mock(side_effect=[None, RuntimeError("storage")])
        with self.assertRaises(RuntimeError):
            embedding.embed_texts(["x"], observation_sink=sink)
        self.client.post.assert_called_once()

    def test_query_service_passes_sink_without_extra_requests(self):
        self.enterContext(patch.object(retrieval_service, "SessionLocal"))
        self.enterContext(patch.object(retrieval_service, "get_repository", return_value=object()))
        self.enterContext(patch.object(retrieval_service, "search_code_chunks", return_value=[]))
        retrieval_service.semantic_search(UUID(int=1), query="question", observation_sink=self.records.append)
        self.client.post.assert_called_once()
        self.assertEqual(len(self.records), 2)


class ConditionsTests(unittest.TestCase):
    def test_legacy_does_not_capture_live_config(self):
        with patch.object(runtime_conditions, "capture_runtime_conditions") as capture:
            runtime_conditions.require_runtime_conditions(AgentRunConfig())
        capture.assert_not_called()

    def test_runtime_drift_is_rejected(self):
        cfg = AgentRunConfig(runtime_fingerprint=runtime_conditions.fingerprint({"model": "before"}))
        with patch.object(runtime_conditions, "capture_runtime_conditions", return_value={"model": "after"}):
            with self.assertRaises(TaskStateConflictError):
                runtime_conditions.require_runtime_conditions(cfg)

    def test_snapshot_is_non_secret_and_deterministic(self):
        with patch.object(runtime_conditions.config, "DASHSCOPE_API_KEY", "should-not-be-saved"):
            first = runtime_conditions.capture_runtime_conditions()
            second = runtime_conditions.capture_runtime_conditions()
        self.assertEqual(first, second)
        self.assertNotIn("should-not-be-saved", str(first))
        self.assertIsNone(first["provider_internal_version"])

    def test_missing_docker_is_explicit_not_fabricated_identity(self):
        with patch.object(conditions.subprocess, "run", side_effect=FileNotFoundError), patch.object(conditions, "capture_index_fingerprint", return_value="a" * 64):
            snapshot = conditions.capture_experiment_conditions(UUID(int=1), test_profile="python-basic")
        self.assertIsNone(snapshot["test_image"]["id"])
        self.assertEqual(snapshot["test_image"]["error_type"], "FileNotFoundError")

    def test_changed_index_stops_before_embedding(self):
        with patch.object(conditions, "capture_index_fingerprint", return_value="b" * 64), patch.object(tool_service, "semantic_search") as search:
            with self.assertRaises(TaskStateConflictError):
                tool_service.execute_readonly_tool(UUID(int=1), tool_name="search_code", arguments={"query": "x"}, run_config=AgentRunConfig(index_fingerprint="a" * 64))
        search.assert_not_called()


class ObservationReportTests(unittest.TestCase):
    def event(self, sequence, suffix, observation=None):
        return SimpleNamespace(sequence=sequence, node_name="query_embedding", event_type="EMBEDDING_CALL_" + suffix,
            payload={"call_id": "request", "scope": "task_query", "model_observation": observation})

    def test_pairs_once_and_preserves_scope(self):
        observation = {"call_id": "request", "usage": {"input_tokens": 8}}
        rows = collect_request_observations([self.event(1, "STARTED"), self.event(2, "COMPLETED", observation)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["scope"], "task_query")
        self.assertEqual(rows[0]["completeness"], "recorded")
        self.assertEqual(rows[0]["observation"], observation)

    def test_missing_and_duplicate_terminal_are_not_counted_as_complete(self):
        self.assertEqual(collect_request_observations([self.event(1, "STARTED")])[0]["completeness"], "missing_terminal")
        rows = collect_request_observations([self.event(1, "STARTED"), self.event(2, "COMPLETED", {"call_id": "request"}), self.event(3, "FAILED")])
        self.assertEqual(rows[0]["completeness"], "ambiguous")
        self.assertIsNone(rows[0]["observation"])

    def test_legacy_terminal_stays_unknown(self):
        row = collect_request_observations([self.event(1, "STARTED"), self.event(2, "COMPLETED")])[0]
        self.assertEqual(row["completeness"], "legacy_or_missing")
