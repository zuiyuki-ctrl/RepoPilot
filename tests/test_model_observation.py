import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

import httpx

from backend.app.rag import generation
from backend.app.rag.model_observation import ModelObservation
from backend.app.agent import nodes, edit_generation, reflection_generation
from backend.app.agent.context import AgentRunContext
from backend.app.schemas.plan import ChangePlan
from backend.app.schemas.testing import TestExecutionEventPayload
from backend.app.services import model_observation_service as persistence
from backend.app.services import edit_proposal_service, reflection_service


class ModelObservationTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.multiple(generation.config, DASHSCOPE_API_KEY="fixture-key",
                                        CHAT_MODEL="requested", CHAT_BASE_URL="https://example.invalid/v1"))
        self.client = self.enterContext(patch.object(generation.httpx, "Client")).return_value.__enter__.return_value
        self.payload = {"id": "response-1", "model": "resolved-model", "usage": {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
            "prompt_tokens_details": {"cached_tokens": 3},
        }, "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]}
        self.messages = [{"role": "user", "content": "private source"}]
        self.respond()

    def respond(self, status=200):
        self.client.post.return_value = httpx.Response(status, json=self.payload,
            request=httpx.Request("POST", "https://example.invalid/v1/chat/completions"))

    def call(self, observation):
        return generation.request_tool_turn(self.messages, observation=observation)

    def test_usage_and_actual_parameters_stay_out_of_message(self):
        observation = ModelObservation()
        message = self.call(observation)
        self.assertEqual(message, {"role": "assistant", "content": "ok"})
        self.assertEqual(observation.usage_status, "complete")
        self.assertEqual(observation.usage["input_tokens"], 10)
        self.assertEqual(observation.usage["cached_input_tokens"], 3)
        self.assertEqual(observation.response_model, "resolved-model")
        self.assertEqual(observation.response_id, "response-1")
        self.assertEqual(observation.request_parameters["max_tokens"], 3000)
        serialized = json.dumps(observation.to_payload())
        self.assertNotIn("fixture-key", serialized)
        self.assertNotIn("private source", serialized)
        self.assertGreaterEqual(observation.duration_ms, 0)
        self.assertEqual(self.client.post.call_count, 1)

    def test_missing_partial_invalid_and_inconsistent_usage(self):
        for usage, status in [(None, "missing"), ({"prompt_tokens": 0}, "partial"),
                              ({"prompt_tokens": True, "completion_tokens": -1}, "invalid"),
                              ({"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 9}, "inconsistent")]:
            with self.subTest(status=status):
                self.payload["usage"] = usage
                self.respond()
                observation = ModelObservation()
                self.call(observation)
                self.assertEqual(observation.usage_status, status)
                self.assertIsNone(observation.usage["cached_input_tokens"])

    def test_timeout_retains_unknown_usage_and_original_exception(self):
        error = httpx.ReadTimeout("private error detail")
        self.client.post.side_effect = error
        observation = ModelObservation()
        with self.assertRaises(httpx.ReadTimeout) as caught:
            self.call(observation)
        self.assertIs(caught.exception, error)
        record = observation.to_payload(error)
        self.assertEqual(record["failure_stage"], "transport")
        self.assertIsNone(record["usage"]["total_tokens"])
        self.assertNotIn("private error detail", json.dumps(record))

    def test_http_and_json_errors_are_distinguished(self):
        self.respond(status=429)
        observation = ModelObservation()
        with self.assertRaises(httpx.HTTPStatusError):
            self.call(observation)
        self.assertEqual(observation.failure_stage, "http_status")
        self.assertEqual(observation.http_status, 429)
        self.assertEqual(observation.usage["total_tokens"], 15)
        self.client.post.return_value = httpx.Response(200, content=b"not json",
            request=httpx.Request("POST", "https://example.invalid"))
        observation = ModelObservation()
        with self.assertRaises(ValueError):
            self.call(observation)
        self.assertEqual(observation.failure_stage, "response_json")

    def test_truncated_response_keeps_tokens(self):
        self.payload["choices"][0]["finish_reason"] = "length"
        self.respond()
        observation = ModelObservation()
        with self.assertRaises(ValueError) as caught:
            self.call(observation)
        record = observation.to_payload(caught.exception)
        self.assertEqual(record["request_status"], "response_received")
        self.assertEqual(record["failure_stage"], "response_validation")
        self.assertEqual(record["usage"]["total_tokens"], 15)

    def test_observation_cannot_be_reused(self):
        observation = ModelObservation()
        self.call(observation)
        with self.assertRaisesRegex(ValueError, "cannot be reused"):
            self.call(observation)
        self.assertEqual(self.client.post.call_count, 1)
        other = ModelObservation()
        self.payload.pop("usage")
        self.respond()
        self.call(other)
        self.assertEqual(other.usage_status, "missing")
        self.assertNotEqual(observation.call_id, other.call_id)

    def test_research_event_reuses_call_id_and_captures_usage(self):
        sink = Mock()
        runtime = SimpleNamespace(context=AgentRunContext(event_sink=sink), execution_info=None)
        state = dict(used_calls=0, max_tool_calls=4, output_exhausted=False,
                     remaining_chars=40000, messages=self.messages)
        result = nodes.model_node(state, runtime)
        events = [c.kwargs for c in sink.call_args_list]
        self.assertEqual([e["event_type"] for e in events], ["MODEL_CALL_STARTED", "MODEL_CALL_COMPLETED"])
        record = events[1]["payload"]["model_observation"]
        self.assertEqual(record["call_id"], events[0]["payload"]["call_id"])
        self.assertEqual(record["usage"]["total_tokens"], 15)
        self.assertNotIn("usage", result["messages"][-1])

    def test_plan_schema_failure_keeps_usage_in_failed_event(self):
        sink = Mock()
        runtime = SimpleNamespace(context=AgentRunContext(event_sink=sink), execution_info=None)
        state = {"sources": [dict(source_id="S1", file_path="a.py", start_line=1, end_line=2)],
                 "messages": self.messages, "user_request": "修复 a.py"}
        with self.assertRaises(ValueError):
            nodes.plan_node(state, runtime)
        event = sink.call_args.kwargs
        self.assertEqual(event["event_type"], "MODEL_CALL_FAILED")
        record = event["payload"]["model_observation"]
        self.assertEqual(record["failure_stage"], "business_validation")
        self.assertEqual(record["usage"]["total_tokens"], 15)

    def test_edit_and_reflection_pass_observation_through_business_failure(self):
        plan = ChangePlan(summary="修复", steps=[dict(id=1, description="修改", files=["a.py"], source_ids=["S1"], verification="测试")])
        result = TestExecutionEventPayload(step_id="tests", attempt=1, passed=False, exit_code=1,
            timed_out=False, stdout="failed", stderr="", stdout_truncated=False, stderr_truncated=False,
            sequence=5, schema_version=1)
        for call in [lambda o: edit_generation.generate_file_edit("修复", plan=plan, file_path="a.py", original_content="pass", observation=o),
                     lambda o: reflection_generation.generate_reflection_decision("修复", plan=plan, test_result=result, observation=o)]:
            observation = ModelObservation()
            with self.assertRaises(ValueError):
                call(observation)
            self.assertEqual(observation.validation_stage, "business_validation")
            self.assertEqual(observation.usage["total_tokens"], 15)

    def test_service_observation_is_persisted_once_per_terminal_event(self):
        with patch.object(persistence, "_persist") as save:
            with persistence.observe_task_model(UUID(int=1), phase="edit") as observation:
                self.call(observation)
            self.assertEqual(save.call_count, 2)
            start, end = save.call_args_list
            self.assertEqual(start.args[3]["call_id"], end.args[3]["call_id"])
            self.assertEqual(end.args[3]["model_observation"]["usage"]["total_tokens"], 15)

    def test_persistence_failure_never_retries_model(self):
        with patch.object(persistence, "_persist", side_effect=[None, RuntimeError("storage")]):
            with self.assertRaisesRegex(RuntimeError, "storage"):
                with persistence.observe_task_model(UUID(int=1), phase="edit") as observation:
                    self.call(observation)
        self.assertEqual(self.client.post.call_count, 1)

    def test_failed_operation_preserves_original_error_if_event_write_fails(self):
        original = ValueError("private invalid plan")
        with patch.object(persistence, "_persist", side_effect=[None, RuntimeError("storage")]):
            with self.assertLogs(persistence.logger, level="ERROR"):
                with self.assertRaises(ValueError) as caught:
                    with persistence.observe_task_model(UUID(int=1), phase="reflection"):
                        raise original
        self.assertIs(caught.exception, original)
        self.client.post.assert_not_called()

    def test_edit_service_records_business_failure_with_usage(self):
        service = edit_proposal_service
        task_id, repository_id = UUID(int=1), UUID(int=2)
        task = SimpleNamespace(task_type="plan", status="executing", review_decision="approved",
            repository_id=repository_id, user_request="修复", result={"repository_id": str(repository_id),
            "plan": {"summary": "修复", "steps": [dict(id=1, description="修改", files=["a.py"], source_ids=["S1"], verification="测试")]}})
        self.enterContext(patch.object(service, "SessionLocal"))
        self.enterContext(patch.object(service, "get_task", return_value=task))
        self.enterContext(patch.object(service, "get_repository", return_value=SimpleNamespace(id=repository_id, workspace_path="D:/fixture")))
        self.enterContext(patch.object(service, "resolve_workspace_target"))
        self.enterContext(patch.object(service, "read_file_snapshot", return_value=SimpleNamespace(content=b"pass", metadata=SimpleNamespace(file_hash="hash"))))
        save = self.enterContext(patch.object(persistence, "_persist"))
        with self.assertRaises(ValueError):
            service.generate_task_file_edit(task_id, file_path="a.py")
        self.assertEqual(save.call_args.args[:3], (task_id, "edit", "MODEL_CALL_FAILED"))
        self.assertEqual(save.call_args.args[3]["model_observation"]["usage"]["total_tokens"], 15)

    def test_reflection_service_records_usage_before_restoring_task(self):
        service = reflection_service
        task_id = UUID(int=1)
        plan = ChangePlan(summary="修复", steps=[dict(id=1, description="修改", files=["a.py"], source_ids=["S1"], verification="测试")])
        test_result = TestExecutionEventPayload(step_id="tests", attempt=1, passed=False, exit_code=1,
            timed_out=False, stdout="failed", stderr="", stdout_truncated=False, stderr_truncated=False,
            sequence=5, schema_version=1)
        context = SimpleNamespace(task_id=task_id, retry_count=1, user_request="修复", plan=SimpleNamespace(plan=plan), test_result=test_result)
        self.enterContext(patch.object(service, "begin_task_reflection", return_value=context))
        restore = self.enterContext(patch.object(service, "_fail_task_reflection"))
        save = self.enterContext(patch.object(persistence, "_persist"))
        with self.assertRaises(ValueError):
            service.run_task_reflection(task_id)
        self.assertEqual(save.call_args.args[:3], (task_id, "reflection", "MODEL_CALL_FAILED"))
        self.assertEqual(save.call_args.args[3]["model_observation"]["usage"]["total_tokens"], 15)
        restore.assert_called_once()
