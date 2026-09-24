from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from backend.app.agent import plan_generation
from backend.app.agent.policy import PLAN_FINAL_INSTRUCTION, PLAN_SYSTEM_PROMPT
from backend.app.core.exceptions import InvalidPlanError
from backend.app.schemas.agent import AgentSourceReference
from backend.app.schemas.plan import ChangePlan


# 测试计划请求的组装与校验；不访问网络、不读取或修改仓库源码。
class GenerateChangePlanTests(unittest.TestCase):
    def setUp(self):
        # 创建 S1 来源。
        self.sources = [
            AgentSourceReference(
                source_id="S1",
                file_path="backend/app/example.py",
                start_line=1,
                end_line=2,
            )
        ]
        # 创建配对的 assistant tool_calls 消息和 tool 源码消息。
        self.evidence_messages = [
            {"role": "system", "content": "旧的系统提示不应被保留。"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "read_source",
                            "arguments": '{"file_path":"backend/app/example.py"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": json.dumps(
                    {
                        "source_id": "S1",
                        "file_path": "backend/app/example.py",
                        "start_line": 1,
                        "end_line": 2,
                        "content": "def example():\n    return 1\n",
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        request_patch = patch.object(plan_generation, "request_tool_turn")
        self.request_tool_turn = request_patch.start()
        self.addCleanup(request_patch.stop)
        self.request_tool_turn.return_value = {
            "role": "assistant",
            "content": self.valid_plan_content(),
        }

    def valid_plan_content(self):
        # 返回可被 parse_change_plan 接受的 JSON 字符串。
        return json.dumps(
            {
                "summary": "调整示例实现",
                "steps": [
                    {
                        "id": 1,
                        "description": "修改示例函数",
                        "files": ["backend/app/example.py"],
                        "source_ids": ["S1"],
                        "verification": "运行单元测试并确认通过",
                    }
                ],
            },
            ensure_ascii=False,
        )

    def generate(self, user_request="修改示例函数"):
        return plan_generation.generate_change_plan(
            user_request,
            evidence_messages=self.evidence_messages,
            sources=self.sources,
        )

    def test_valid_json_returns_change_plan(self):
        # patch plan_generation.request_tool_turn。
        result = self.generate()
        # 断言返回 ChangePlan。
        self.assertIsInstance(result, ChangePlan)
        self.assertEqual(result.summary, "调整示例实现")
        # 断言 allow_tools=False。
        _, kwargs = self.request_tool_turn.call_args
        self.assertIs(kwargs["allow_tools"], False)
        # 断言 final_instruction 是 PLAN_FINAL_INSTRUCTION。
        self.assertIs(kwargs["final_instruction"], PLAN_FINAL_INSTRUCTION)

    def test_invalid_model_plans_are_rejected(self):
        # 分别返回非 JSON 和引用 S99 的 JSON。
        unknown_source_plan = json.loads(self.valid_plan_content())
        unknown_source_plan["steps"][0]["source_ids"] = ["S99"]
        invalid_contents = (
            "这不是 JSON",
            json.dumps(unknown_source_plan, ensure_ascii=False),
        )
        for content in invalid_contents:
            with self.subTest(content=content):
                self.request_tool_turn.reset_mock()
                self.request_tool_turn.return_value = {
                    "role": "assistant",
                    "content": content,
                }
                # 断言抛 InvalidPlanError。
                with self.assertRaises(InvalidPlanError):
                    self.generate()
                self.request_tool_turn.assert_called_once()

    def test_invalid_inputs_do_not_call_model(self):
        # 覆盖空白需求、超长需求、空 evidence_messages、空 sources。
        cases = (
            ("blank request", " \n", self.evidence_messages, self.sources),
            ("long request", "x" * 1001, self.evidence_messages, self.sources),
            ("empty evidence", "修改示例函数", [], self.sources),
            ("empty sources", "修改示例函数", self.evidence_messages, []),
        )
        # 每个子用例使用 reset_mock。
        for name, user_request, evidence_messages, sources in cases:
            with self.subTest(name=name):
                self.request_tool_turn.reset_mock()
                with self.assertRaises(ValueError):
                    plan_generation.generate_change_plan(
                        user_request,
                        evidence_messages=evidence_messages,
                        sources=sources,
                    )
                # 断言 request_tool_turn 没有被调用。
                self.request_tool_turn.assert_not_called()

    def test_network_error_is_propagated(self):
        # 创建一个具体异常对象作为 side_effect。
        network_error = RuntimeError("network unavailable")
        self.request_tool_turn.side_effect = network_error
        # 使用 assertRaises 检查异常类型。
        with self.assertRaises(RuntimeError) as raised:
            self.generate()
        # 进一步断言捕获到的对象就是原异常对象。
        self.assertIs(raised.exception, network_error)

    def test_request_preserves_evidence_and_contains_schema(self):
        self.generate("  修改示例函数  ")
        messages = self.request_tool_turn.call_args.args[0]

        self.assertEqual(messages[0], {
            "role": "system",
            "content": PLAN_SYSTEM_PROMPT,
        })
        # 检查传给模型的 assistant/tool 消息仍按原顺序存在。
        self.assertEqual(messages[1:-1], self.evidence_messages[1:])
        self.assertIsNot(messages[1], self.evidence_messages[1])
        self.assertIsNot(messages[2], self.evidence_messages[2])
        # 检查源码正文存在。
        serialized_messages = json.dumps(messages, ensure_ascii=False)
        self.assertIn("def example()", serialized_messages)
        # 检查最终用户消息包含来源对象和 Schema 的关键字段。
        request_content = messages[-1]["content"]
        self.assertIn("修改示例函数", request_content)
        self.assertIn('"source_id": "S1"', request_content)
        self.assertIn('"file_path": "backend/app/example.py"', request_content)
        self.assertIn('"summary"', request_content)
        self.assertIn('"steps"', request_content)
        self.assertIn('"source_ids"', request_content)
        self.assertNotIn("旧的系统提示不应被保留", serialized_messages)

    def test_evidence_messages_are_not_modified(self):
        # deepcopy 后调用函数，再断言完全相等。
        before = deepcopy(self.evidence_messages)
        self.generate()
        self.assertEqual(self.evidence_messages, before)


if __name__ == "__main__":
    unittest.main()
