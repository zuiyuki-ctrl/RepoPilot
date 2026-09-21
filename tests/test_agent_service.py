import json
import unittest
from unittest.mock import patch
from uuid import UUID

from backend.app.core.exceptions import InvalidAnswerCitationError, RepositoryScanError
from backend.app.services import agent_service as agent


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
        self.repository = self.start_patch("get_repository", return_value=object())
        self.model = self.start_patch("request_tool_turn")
        self.tool = self.start_patch("execute_readonly_tool")

    def start_patch(self, name, **kwargs):
        patcher = patch.object(agent, name, **kwargs)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def run_agent(self, **kwargs):
        return agent.run_readonly_agent(self.repository_id, question="旧块怎么处理？", **kwargs)

    def tool_messages(self):
        return [message for message in self.model.call_args.args[0] if message["role"] == "tool"]

    def test_missing_repository_does_not_call_model(self):
        self.repository.return_value = None
        self.assertIsNone(self.run_agent())
        self.model.assert_not_called()

    def test_direct_answer_without_evidence_is_replaced(self):
        self.model.return_value = answer_turn("猜测旧块没有删除。[S1]")
        result = self.run_agent()
        self.assertEqual(result["answer"], agent.NO_EVIDENCE_ANSWER)
        self.assertEqual(result["sources"], [])
        self.tool.assert_not_called()

    def test_empty_search_is_not_evidence(self):
        self.model.side_effect = [tool_turn("search_code"), answer_turn()]
        self.tool.return_value = {"hits": []}
        self.assertEqual(self.run_agent()["answer"], agent.NO_EVIDENCE_ANSWER)

    def test_whitespace_source_is_not_evidence(self):
        self.model.side_effect = [tool_turn("read_source"), answer_turn()]
        self.tool.return_value = source_result(" \n")
        self.assertEqual(self.run_agent()["sources"], [])

    def test_source_read_failure_can_be_corrected(self):
        self.model.side_effect = [tool_turn("read_source"), tool_turn("read_source"), answer_turn()]
        self.tool.side_effect = [RepositoryScanError("private filesystem details"), source_result()]
        with self.assertLogs(agent.logger, level="WARNING"):
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
        self.assertEqual(self.run_agent()["answer"], agent.NO_EVIDENCE_ANSWER)

    def test_long_errors_are_bounded_and_json_remains_valid(self):
        self.model.side_effect = [tool_turn("read_source"), answer_turn()]
        self.tool.side_effect = ValueError('"\n' * 5000)
        result = self.run_agent()
        error = result["tool_trace"][0]["result"]["error"]
        self.assertLessEqual(len(error), agent.MAX_TOOL_ERROR_CHARS)
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

    def test_discarded_oversized_source_is_not_evidence(self):
        self.model.side_effect = [tool_turn("read_source"), answer_turn()]
        self.tool.return_value = source_result("x" * 40001)
        result = self.run_agent()
        self.assertEqual(result["answer"], agent.NO_EVIDENCE_ANSWER)
        self.assertIn("error", result["tool_trace"][0]["result"])
        self.assertFalse(self.model.call_args.kwargs["allow_tools"])

    def test_call_limit_preserves_responses_for_all_call_ids(self):
        self.model.side_effect = [tool_turn("read_source", "read_source"), answer_turn()]
        self.tool.return_value = source_result()
        result = self.run_agent(max_tool_calls=1)
        self.assertEqual(self.tool.call_count, 1)
        self.assertEqual(len(result["tool_trace"]), 2)
        self.assertIn("error", result["tool_trace"][1]["result"])
        self.assertFalse(self.model.call_args.kwargs["allow_tools"])

    def test_unserviceable_call_batch_fails_before_tool_execution(self):
        self.model.return_value = tool_turn(*(["read_source"] * 5))
        with patch.object(agent, "MAX_TOOL_RESULT_CHARS", 120):
            with self.assertRaisesRegex(ValueError, "Too many tool calls"):
                self.run_agent()
        self.tool.assert_not_called()

    def test_unexpected_infrastructure_error_is_not_swallowed(self):
        self.model.return_value = tool_turn("search_code")
        self.tool.side_effect = RuntimeError("database unavailable")
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            self.run_agent()


if __name__ == "__main__":
    unittest.main()
