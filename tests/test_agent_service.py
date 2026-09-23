import json
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch
from uuid import UUID

from backend.app.core.exceptions import InvalidAnswerCitationError, RepositoryScanError
from backend.app.services import agent_service as agent
from backend.app.agent import nodes, policy


# 模拟模型消息和工具结果，测试不连接数据库、不读取仓库、不消耗模型额度。
def tool_turn(*names):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call-{index}",
                "type": "function",
                "function": {"name": name, "arguments": "{}"},
            }
            for index, name in enumerate(names)
        ],
    }


def answer_turn(content="根据源码可以确认。[S1]"):
    return {"role": "assistant", "content": content}


def source_result(content="def example():\n    return 1\n"):
    return {"file_path": "example.py", "start_line": 1, "end_line": 2, "content": content}


class ReadonlyAgentTests(unittest.TestCase):
    def setUp(self):
        self.repository_id = UUID("00000000-0000-0000-0000-000000000001")
        self.repository = self.start_patch(agent, "get_repository", return_value=object())
        self.model = self.start_patch(nodes, "request_tool_turn")
        self.tool = self.start_patch(nodes, "execute_readonly_tool")

    def start_patch(self, target, name, **kwargs):
        patcher = patch.object(target, name, **kwargs)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def run_agent(self, **kwargs):
        return agent.run_readonly_agent(self.repository_id, question="旧块怎么处理？", **kwargs)

    def tool_messages(self):
        return [message for message in self.model.call_args.args[0] if message["role"] == "tool"]

    def tool_events(self, sink):
        return [
            call.kwargs
            for call in sink.call_args_list
            if call.kwargs["event_type"].startswith("TOOL_CALL_")
        ]

    # 预算决策和真正的工具执行事件分别检查，避免把跳过误记为执行失败。
    def budget_events(self, sink):
        return [
            call.kwargs
            for call in sink.call_args_list
            if call.kwargs["event_type"] == "BUDGET_EXCEEDED"
        ]

    def test_missing_repository_does_not_call_model(self):
        self.repository.return_value = None
        self.assertIsNone(self.run_agent())
        self.model.assert_not_called()

    def test_direct_answer_without_evidence_is_replaced(self):
        self.model.return_value = answer_turn("猜测旧块没有删除。[S1]")
        result = self.run_agent()
        self.assertEqual(result["answer"], policy.NO_EVIDENCE_ANSWER)
        self.assertEqual(result["sources"], [])
        self.tool.assert_not_called()

    def test_empty_search_is_not_evidence(self):
        self.model.side_effect = [tool_turn("search_code"), answer_turn()]
        self.tool.return_value = {"hits": []}
        self.assertEqual(self.run_agent()["answer"], policy.NO_EVIDENCE_ANSWER)

    def test_whitespace_source_is_not_evidence(self):
        self.model.side_effect = [tool_turn("read_source"), answer_turn()]
        self.tool.return_value = source_result(" \n")
        self.assertEqual(self.run_agent()["sources"], [])

    def test_source_read_failure_can_be_corrected(self):
        self.model.side_effect = [tool_turn("read_source"), tool_turn("read_source"), answer_turn()]
        self.tool.side_effect = [RepositoryScanError("private filesystem details"), source_result()]
        with self.assertLogs(nodes.logger, level="WARNING"):
            result = self.run_agent()
        self.assertEqual(self.tool.call_count, 2)
        self.assertIn("error", result["tool_trace"][0]["result"])
        self.assertNotIn("private filesystem", result["tool_trace"][0]["result"]["error"])
        self.assertEqual(result["sources"][0]["source_id"], "S1")
        self.assertIn("example.py:1-2", result["answer"])

    def test_search_and_read_have_distinct_valid_sources(self):
        self.model.side_effect = [tool_turn("search_code", "read_source"), answer_turn("依据 [S1] 和 [S2]。")]
        self.tool.side_effect = [{"hits": [{"chunk": source_result(), "distance": 0.1}]}, source_result()]
        result = self.run_agent()
        self.assertEqual([source["source_id"] for source in result["sources"]], ["S1", "S2"])
        messages = self.tool_messages()
        self.assertEqual(json.loads(messages[0]["content"])["hits"][0]["chunk"]["source_id"], "S1")
        self.assertEqual(json.loads(messages[1]["content"])["source_id"], "S2")

    def test_missing_or_unknown_citations_are_rejected(self):
        for answer in ("没有引用的回答", "错误引用 [S99]", "混合引用 [S1] [S2]"):
            with self.subTest(answer=answer):
                self.model.side_effect = [tool_turn("read_source"), answer_turn(answer)]
                self.tool.return_value = source_result()
                with self.assertRaises(InvalidAnswerCitationError):
                    self.run_agent()

    def test_tool_errors_without_evidence_cannot_produce_claims(self):
        self.model.side_effect = [tool_turn("read_source"), answer_turn()]
        self.tool.side_effect = ValueError("invalid range")
        self.assertEqual(self.run_agent()["answer"], policy.NO_EVIDENCE_ANSWER)

    def test_long_errors_are_bounded_and_json_remains_valid(self):
        self.model.side_effect = [tool_turn("read_source"), answer_turn()]
        self.tool.side_effect = ValueError('"\n' * 5000)
        result = self.run_agent()
        error = result["tool_trace"][0]["result"]["error"]
        self.assertLessEqual(len(error), policy.MAX_TOOL_ERROR_CHARS)
        self.assertEqual(json.loads(self.tool_messages()[0]["content"])["error"], error)

    def test_errors_consume_budget_and_stop_later_tools(self):
        self.model.side_effect = [tool_turn("read_source", "read_source", "read_source"), answer_turn()]
        self.tool.side_effect = ValueError("x" * 10000)
        with patch.object(agent, "MAX_TOOL_RESULT_CHARS", 120):
            result = self.run_agent()
        self.assertEqual(self.tool.call_count, 1)
        messages = self.tool_messages()
        self.assertEqual(len(messages), 3)
        self.assertLessEqual(sum(len(message["content"]) for message in messages), 120)
        self.assertEqual([message["tool_call_id"] for message in messages], ["call-0", "call-1", "call-2"])
        self.assertFalse(self.model.call_args.kwargs["allow_tools"])
        self.assertEqual(result["sources"], [])

    # 工具实际执行成功但结果超长时，记录丢弃决策，且不能把丢弃的源码作为证据。
    def test_discarded_oversized_source_is_not_evidence(self):
        sink = Mock()
        self.model.side_effect = [tool_turn("read_source"), answer_turn()]
        self.tool.return_value = source_result("x" * 40001)
        result = self.run_agent(event_sink=sink)
        self.assertEqual(result["answer"], policy.NO_EVIDENCE_ANSWER)
        self.assertEqual(result["sources"], [])
        self.assertIn("error", result["tool_trace"][0]["result"])
        self.assertFalse(self.model.call_args.kwargs["allow_tools"])
        self.tool.assert_called_once()
        events = self.budget_events(sink)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["node_name"], "tools")
        payload = events[0]["payload"]
        self.assertEqual(payload["action"], "discard_result")
        self.assertEqual(payload["reason"], "tool_result_chars")
        self.assertIs(payload["attempted"], True)
        self.assertEqual(payload["tool_call_id"], "call-0")
        self.assertGreater(payload["result_chars"], payload["available_chars"])
        self.assertEqual(payload["available_chars"], payload["remaining_chars"] - payload["reserved_chars"])
        tool_events = self.tool_events(sink)
        self.assertEqual(
            [event["event_type"] for event in tool_events],
            ["TOOL_CALL_STARTED", "TOOL_CALL_COMPLETED"],
        )
        self.assertEqual(payload["call_id"], tool_events[0]["payload"]["call_id"])

    def test_call_limit_preserves_responses_for_all_call_ids(self):
        self.model.side_effect = [tool_turn("read_source", "read_source"), answer_turn()]
        self.tool.return_value = source_result()
        result = self.run_agent(max_tool_calls=1)
        self.assertEqual(self.tool.call_count, 1)
        self.assertEqual(len(result["tool_trace"]), 2)
        self.assertIn("error", result["tool_trace"][1]["result"])
        self.assertFalse(self.model.call_args.kwargs["allow_tools"])

    # 连整批最短错误响应都放不下时，记录整批拒绝并保留原有 ValueError。
    def test_unserviceable_call_batch_fails_before_tool_execution(self):
        sink = Mock()
        self.model.return_value = tool_turn(*(["read_source"] * 5))
        with patch.object(agent, "MAX_TOOL_RESULT_CHARS", 120):
            with self.assertRaisesRegex(ValueError, "^Too many tool calls for the remaining tool-result budget$"):
                self.run_agent(event_sink=sink)
        self.tool.assert_not_called()
        self.assertEqual(self.tool_events(sink), [])
        events = self.budget_events(sink)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["node_name"], "tools")
        payload = events[0]["payload"]
        self.assertEqual(payload["action"], "reject_batch")
        self.assertEqual(payload["reason"], "tool_result_chars")
        self.assertIs(payload["attempted"], False)
        self.assertEqual(payload["requested_calls"], 5)
        self.assertEqual(payload["remaining_chars"], 120)
        self.assertEqual(payload["required_chars"], 5 * len(json.dumps(policy.BUDGET_ERROR, ensure_ascii=False)))
        self.assertGreater(payload["required_chars"], payload["remaining_chars"])
        self.assertIsInstance(payload["attempt"], int)
        self.assertGreaterEqual(payload["attempt"], 1)
        # 事件会写入 JSON，不能残留 Ellipsis 等不可序列化的占位值。
        json.dumps(events, ensure_ascii=False)

    def test_unexpected_infrastructure_error_is_not_swallowed(self):
        self.model.return_value = tool_turn("search_code")
        self.tool.side_effect = RuntimeError("database unavailable")
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            self.run_agent()

    # 一次成功的模型请求必须产生开始/完成事件，并使用同一个有效调用 ID。
    def test_model_events_share_call_id(self):
        sink = Mock()
        self.model.return_value = answer_turn()

        with patch.object(nodes, "perf_counter", side_effect=[10.0, 10.125]):
            result = self.run_agent(event_sink=sink)

        self.model.assert_called_once()
        self.tool.assert_not_called()
        self.assertEqual(result["answer"], policy.NO_EVIDENCE_ANSWER)
        events = [call.kwargs for call in sink.call_args_list]
        self.assertEqual(
            [event["event_type"] for event in events],
            ["MODEL_CALL_STARTED", "MODEL_CALL_COMPLETED"],
        )
        started, completed = events
        self.assertEqual(started["node_name"], "model")
        self.assertEqual(completed["node_name"], "model")
        started_payload = started["payload"]
        completed_payload = completed["payload"]
        self.assertEqual(str(UUID(started_payload["call_id"])), started_payload["call_id"])
        self.assertEqual(started_payload["call_id"], completed_payload["call_id"])
        self.assertEqual(started_payload["step_id"], "model")
        self.assertEqual(completed_payload["step_id"], "model")
        self.assertGreaterEqual(started_payload["attempt"], 1)
        self.assertEqual(started_payload["attempt"], completed_payload["attempt"])
        self.assertTrue(started_payload["allow_tools"])
        self.assertEqual(completed_payload["response_type"], "answer")
        self.assertEqual(completed_payload["tool_call_count"], 0)
        self.assertEqual(completed_payload["duration_ms"], 125)

    # 模型失败时记录异常类型及耗时，不把可能含敏感内容的异常原文写进事件。
    def test_model_failure_emits_failed_event(self):
        sink = Mock()
        model_error = RuntimeError("private model response must not appear in events")
        self.model.side_effect = model_error

        with patch.object(nodes, "perf_counter", side_effect=[20.0, 20.25]):
            with self.assertRaises(RuntimeError) as caught:
                self.run_agent(event_sink=sink)

        self.assertIs(caught.exception, model_error)
        self.model.assert_called_once()
        self.tool.assert_not_called()
        events = [call.kwargs for call in sink.call_args_list]
        self.assertEqual(
            [event["event_type"] for event in events],
            ["MODEL_CALL_STARTED", "MODEL_CALL_FAILED"],
        )
        started, failed = events
        self.assertEqual(failed["node_name"], "model")
        self.assertEqual(failed["payload"]["call_id"], started["payload"]["call_id"])
        self.assertEqual(failed["payload"]["step_id"], started["payload"]["step_id"])
        self.assertEqual(failed["payload"]["attempt"], started["payload"]["attempt"])
        self.assertEqual(failed["payload"]["duration_ms"], 250)
        self.assertEqual(failed["payload"]["error_type"], "RuntimeError")
        self.assertNotIn(str(model_error), json.dumps(events, ensure_ascii=False))

    # 记录失败事件再次出错时，只记录日志，不能用事件存储异常覆盖原始模型异常。
    def test_failed_event_write_preserves_model_error(self):
        model_error = RuntimeError("original model failure")
        event_error = RuntimeError("event write failed")
        self.model.side_effect = model_error
        sink = Mock(side_effect=[None, event_error])

        with self.assertLogs(nodes.logger, level="ERROR") as logs:
            with self.assertRaises(RuntimeError) as caught:
                self.run_agent(event_sink=sink)

        self.assertIs(caught.exception, model_error)
        self.model.assert_called_once()
        self.tool.assert_not_called()
        events = [call.kwargs for call in sink.call_args_list]
        self.assertEqual(
            [event["event_type"] for event in events],
            ["MODEL_CALL_STARTED", "MODEL_CALL_FAILED"],
        )
        self.assertEqual(events[0]["payload"]["call_id"], events[1]["payload"]["call_id"])
        self.assertTrue(any("Failed to persist model failure event" in record.getMessage() for record in logs.records))
        self.assertTrue(any(record.exc_info and record.exc_info[1] is event_error for record in logs.records))

    # 一次成功工具执行对应一对事件，内部 call_id 和模型的 tool_call_id 都需匹配。
    def test_tool_success_events_share_call_id(self):
        sink = Mock()
        self.model.side_effect = [
            tool_turn("read_source"),
            answer_turn(),
        ]
        self.tool.return_value = source_result()

        self.run_agent(event_sink=sink)
        events = self.tool_events(sink)

        self.assertEqual(
            [event["event_type"] for event in events],
            ["TOOL_CALL_STARTED", "TOOL_CALL_COMPLETED"],
        )
        started, completed = events
        self.assertEqual(started["payload"]["call_id"], completed["payload"]["call_id"])
        self.assertEqual(str(UUID(started["payload"]["call_id"])), started["payload"]["call_id"])
        for event in events:
            self.assertEqual(event["node_name"], "tools")
            self.assertEqual(event["payload"]["tool_call_id"], "call-0")
            self.assertEqual(event["payload"]["tool_name"], "read_source")
        self.assertGreaterEqual(completed["payload"]["duration_ms"], 0)
        self.tool.assert_called_once()

    # 可恢复错误要记录失败事件并反馈给模型，不应提前终止 Agent。
    def test_recoverable_tool_error_emits_failed_event(self):
        sink = Mock()
        self.model.side_effect = [
            tool_turn("read_source"),
            answer_turn(),
        ]
        self.tool.side_effect = ValueError("invalid range")

        result = self.run_agent(event_sink=sink)
        events = self.tool_events(sink)

        self.assertEqual(
            [event["event_type"] for event in events],
            ["TOOL_CALL_STARTED", "TOOL_CALL_FAILED"],
        )
        started, failed = events
        self.assertEqual(failed["payload"]["error_type"], "ValueError")
        self.assertIs(failed["payload"]["recoverable"], True)
        self.assertEqual(started["payload"]["call_id"], failed["payload"]["call_id"])
        self.assertGreaterEqual(failed["payload"]["duration_ms"], 0)
        self.assertNotIn("invalid range", json.dumps(events, ensure_ascii=False))
        self.assertIn("error", result["tool_trace"][0]["result"])
        self.assertEqual(result["answer"], policy.NO_EVIDENCE_ANSWER)
        self.assertEqual(self.model.call_count, 2)
        self.tool.assert_called_once()

    # 超预算调用没有真正执行，因此不产生执行事件，但仍需回复对应的工具消息。
    def test_budget_rejected_tool_has_no_execution_events(self):
        sink = Mock()
        self.model.side_effect = [
            tool_turn("read_source", "read_source"),
            answer_turn(),
        ]
        self.tool.return_value = source_result()

        result = self.run_agent(max_tool_calls=1, event_sink=sink)
        events = self.tool_events(sink)

        self.tool.assert_called_once()
        self.assertEqual(
            [event["event_type"] for event in events],
            ["TOOL_CALL_STARTED", "TOOL_CALL_COMPLETED"],
        )
        for event in events:
            self.assertEqual(event["payload"]["tool_call_id"], "call-0")
        budget_events = self.budget_events(sink)
        self.assertEqual(len(budget_events), 1)
        self.assertEqual(budget_events[0]["node_name"], "tools")
        payload = budget_events[0]["payload"]
        self.assertEqual(payload["action"], "skip_tool")
        self.assertEqual(payload["reason"], "tool_calls")
        self.assertIs(payload["attempted"], False)
        self.assertEqual(payload["tool_call_id"], "call-1")
        self.assertEqual(payload["tool_name"], "read_source")
        self.assertEqual(len(result["tool_trace"]), 2)
        rejected = result["tool_trace"][1]
        self.assertEqual(rejected["tool_call_id"], "call-1")
        self.assertEqual(rejected["result"], policy.BUDGET_ERROR)
        self.assertEqual(
            [message["tool_call_id"] for message in self.tool_messages()],
            ["call-0", "call-1"],
        )

    # 不可恢复错误必须原样抛出，即便失败事件的写入也失败，仍保留原始异常对象。
    def test_tool_failure_preserves_original_error(self):
        for sink_fails in (False, True):
            with self.subTest(sink_fails=sink_fails):
                self.model.reset_mock()
                self.tool.reset_mock()
                tool_error = RuntimeError("original tool failure")
                event_error = RuntimeError("event write failed")
                self.model.side_effect = None
                self.model.return_value = tool_turn("read_source")
                self.tool.side_effect = tool_error

                def record_event(**kwargs):
                    if sink_fails and kwargs["event_type"] == "TOOL_CALL_FAILED":
                        raise event_error

                sink = Mock(side_effect=record_event)

                log_context = self.assertLogs(nodes.logger, level="ERROR") if sink_fails else nullcontext()
                with log_context as logs:
                    with self.assertRaises(RuntimeError) as caught:
                        self.run_agent(event_sink=sink)

                self.assertIs(caught.exception, tool_error)
                self.model.assert_called_once()
                self.tool.assert_called_once()
                events = self.tool_events(sink)
                self.assertEqual(
                    [event["event_type"] for event in events],
                    ["TOOL_CALL_STARTED", "TOOL_CALL_FAILED"],
                )
                started, failed = events
                self.assertIs(failed["payload"]["recoverable"], False)
                self.assertEqual(failed["payload"]["error_type"], "RuntimeError")
                self.assertEqual(started["payload"]["call_id"], failed["payload"]["call_id"])
                self.assertEqual(failed["payload"]["tool_call_id"], "call-0")
                self.assertGreaterEqual(failed["payload"]["duration_ms"], 0)
                self.assertNotIn(str(tool_error), json.dumps(events, ensure_ascii=False))
                if sink_fails:
                    self.assertTrue(any(
                        "Failed to persist tool failure event" in record.getMessage()
                        and record.exc_info and record.exc_info[1] is event_error
                        for record in logs.records
                    ))

if __name__ == "__main__":
    unittest.main()
