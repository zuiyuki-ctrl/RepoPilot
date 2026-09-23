from copy import deepcopy
import unittest
from unittest.mock import patch

from backend.app.rag import generation


# 模拟 HTTP 客户端，检查真正发出的请求体及响应校验，不访问外部模型。
class RequestToolTurnTests(unittest.TestCase):
    def setUp(self):
        config_patch = patch.multiple(
            generation.config,
            DASHSCOPE_API_KEY="test-key",
            CHAT_BASE_URL="https://example.invalid/v1",
            CHAT_MODEL="test-model",
        )
        config_patch.start()
        self.addCleanup(config_patch.stop)
        client_patch = patch.object(generation.httpx, "Client")
        self.client = client_patch.start().return_value.__enter__.return_value
        self.addCleanup(client_patch.stop)
        self.tool_call = {
            "id": "call-1",
            "type": "function",
            "function": {"name": "read_source", "arguments": '{"file_path":"example.py"}'},
        }
        self.messages = [
            {"role": "system", "content": "基于代码证据回答。"},
            {"role": "user", "content": "解释这个函数。"},
            {"role": "assistant", "content": None, "tool_calls": [self.tool_call]},
            {"role": "tool", "tool_call_id": "call-1", "content": '{"source_id":"S1","content":"pass"}'},
        ]
        self.set_response("stop", {"role": "assistant", "content": "根据证据 [S1]。"})

    def set_response(self, finish_reason, message):
        self.client.post.return_value.json.return_value = {
            "choices": [{"finish_reason": finish_reason, "message": message}]
        }

    # 正常调用保留工具定义、自动选择及既有生成参数，不额外添加收尾消息。
    def test_enabled_tools_preserve_request_parameters(self):
        before = deepcopy(self.messages)
        generation.request_tool_turn(self.messages, allow_tools=True)
        body = self.client.post.call_args.kwargs["json"]
        self.assertEqual(body["tools"], generation.TOOL_DEFINITIONS)
        self.assertEqual(body["tool_choice"], "auto")
        self.assertEqual(body["messages"], before)
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(body["max_tokens"], 1500)
        self.assertFalse(body["stream"])
        self.assertFalse(body["enable_thinking"])
        self.assertEqual(self.messages, before)

    # 禁用工具的多次调用都只添加一条收尾指令，不污染调用方历史或破坏工具消息配对。
    def test_disabled_tools_append_instruction_to_copy(self):
        before = deepcopy(self.messages)
        for _ in range(2):
            result = generation.request_tool_turn(self.messages, allow_tools=False)
            body = self.client.post.call_args.kwargs["json"]
            self.assertNotIn("tools", body)
            self.assertNotIn("tool_choice", body)
            self.assertIsNot(body["messages"], self.messages)
            self.assertEqual(body["messages"][:-1], before)
            self.assertEqual(body["messages"][-1], {
                "role": "user",
                "content": "工具预算已耗尽。请仅根据已有证据给出最终回答，使用已有引用编号，明确说明未确认部分，不再请求工具。",
            })
            self.assertEqual(self.messages, before)
            self.assertEqual(result["content"], "根据证据 [S1]。")

    # 无论模型如何标记结束原因，禁用工具时都不能接受携带工具调用的回答。
    def test_disabled_tools_reject_tool_calls(self):
        for finish_reason in ("tool_calls", "stop"):
            with self.subTest(finish_reason=finish_reason):
                self.set_response(finish_reason, {
                    "role": "assistant", "content": "继续调用工具", "tool_calls": [self.tool_call],
                })
                with self.assertRaises(ValueError):
                    generation.request_tool_turn(self.messages, allow_tools=False)

    # 允许工具时，合法调用仍原样交给 Agent 执行。
    def test_enabled_tools_accept_valid_call(self):
        message = {"role": "assistant", "content": None, "tool_calls": [self.tool_call]}
        self.set_response("tool_calls", message)
        self.assertEqual(generation.request_tool_turn(self.messages), message)

    # 收尾分支仍拒绝截断结果和空白答案。
    def test_disabled_tools_preserve_answer_validation(self):
        for finish_reason, content in (("length", "被截断的回答"), ("stop", " \n")):
            with self.subTest(finish_reason=finish_reason):
                self.set_response(finish_reason, {"role": "assistant", "content": content})
                with self.assertRaises(ValueError):
                    generation.request_tool_turn(self.messages, allow_tools=False)


if __name__ == "__main__":
    unittest.main()
