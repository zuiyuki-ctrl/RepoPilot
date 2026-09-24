import json
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from backend.app.services import agent_service as agent
from backend.app.agent import nodes, plan_generation
from backend.app.core.exceptions import InvalidPlanError, InsufficientPlanEvidenceError
from backend.app.schemas.plan import ChangePlan

class PlanningAgentTests(unittest.TestCase):
    def setUp(self):
        self.repository_id = UUID("00000000-0000-0000-0000-000000000001")
        self.user_request = "为示例函数补充边界测试"
        self.repository = self.start_patch(agent, "get_repository", return_value=object())
        self.research_model = self.start_patch(nodes, "request_tool_turn")
        self.tool = self.start_patch(nodes, "execute_readonly_tool")
        self.plan_model = self.start_patch(plan_generation, "request_tool_turn")
        self.research_messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "research-call-1",
                    "type": "function",
                    "function": {
                        "name": "read_source",
                        "arguments": json.dumps({"file_path": "example.py", "start_line": 1, "end_line": 2}),
                    },
                }],
            },
            {"role": "assistant", "content": "已完成研究，可以生成计划。"},
        ]
        self.research_model.side_effect = self.research_messages
        self.tool.return_value = {
            "file_path": "example.py",
            "start_line": 1,
            "end_line": 2,
            "content": "def example():\n    return 1\n",
        }
        self.plan_payload = {
            "summary": "补充示例函数测试",
            "steps": [{
                "id": 1,
                "description": "新建单元测试覆盖示例函数的返回值",
                "files": ["tests/test_example.py"],
                "source_ids": ["S1"],
                "verification": "运行新增单元测试并确认通过",
            }],
        }
        self.plan_model.return_value = {
            "role": "assistant",
            "content": json.dumps(self.plan_payload, ensure_ascii=False),
        }

    # 仅替换仓库查询、工具和两阶段模型请求，保留真实 Graph、证据整理及计划校验。
    def start_patch(self, target, name, **kwargs):
        patcher = patch.object(target, name, **kwargs)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def run_agent(self, **kwargs):
        return agent.run_planning_agent(
            self.repository_id, user_request=self.user_request, **kwargs
        )

    # 研究阶段也会产生模型事件；这里仅筛选计划节点的事件，避免错误配对。
    def plan_events(self, sink):
        return [call.kwargs for call in sink.call_args_list if call.kwargs["node_name"] == "plan"]

    # 研究取得的真实工具证据应传入计划阶段，并最终返回经过解析器校验的计划。
    def test_research_to_plan_succeeds(self):
        sink = Mock()
        result = self.run_agent(event_sink=sink)

        self.assertIsInstance(result, ChangePlan)
        self.assertEqual(result.model_dump(mode="json"), self.plan_payload)
        self.repository.assert_called_once_with(self.repository_id)
        self.assertEqual(self.research_model.call_count, 2)
        self.tool.assert_called_once_with(
            self.repository_id,
            tool_name="read_source",
            arguments={"file_path": "example.py", "start_line": 1, "end_line": 2},
        )
        self.plan_model.assert_called_once()
        request = self.plan_model.call_args
        self.assertIs(request.kwargs["allow_tools"], False)
        self.assertEqual(request.kwargs["final_instruction"], plan_generation.PLAN_FINAL_INSTRUCTION)
        messages = request.args[0]
        self.assertEqual(messages[0], {"role": "system", "content": plan_generation.PLAN_SYSTEM_PROMPT})
        self.assertEqual(sum(message["role"] == "system" for message in messages), 1)
        tool_messages = [message for message in messages if message["role"] == "tool"]
        self.assertEqual(len(tool_messages), 1)
        evidence = json.loads(tool_messages[0]["content"])
        self.assertEqual(evidence["source_id"], "S1")
        self.assertEqual(evidence["content"], self.tool.return_value["content"])
        self.assertEqual(tool_messages[0]["tool_call_id"], "research-call-1")
        self.assertIn(self.user_request, messages[-1]["content"])

        events = self.plan_events(sink)
        self.assertEqual([event["event_type"] for event in events], [
            "MODEL_CALL_STARTED", "MODEL_CALL_COMPLETED", "PLAN_CREATED",
        ])
        started, completed, created = [event["payload"] for event in events]
        self.assertEqual(str(UUID(started["call_id"])), started["call_id"])
        for payload in (completed, created):
            self.assertEqual(payload["call_id"], started["call_id"])
            self.assertEqual(payload["attempt"], started["attempt"])
            self.assertEqual(payload["step_id"], "plan")
        self.assertIs(started["allow_tools"], False)
        self.assertGreaterEqual(completed["duration_ms"], 0)
        self.assertEqual(completed["response_type"], "plan")
        self.assertEqual(completed["tool_call_count"], 0)
        self.assertEqual(created["plan"], result.model_dump(mode="json"))
        self.assertEqual(created["sources"], [{
            "source_id": "S1", "file_path": "example.py", "start_line": 1, "end_line": 2,
        }])

    # 不存在的仓库在研究前就结束，不产生事件或任何模型/工具调用。
    def test_missing_repository_stops_before_model(self):
        sink = Mock()
        self.repository.return_value = None
        self.assertIsNone(self.run_agent(event_sink=sink))
        self.research_model.assert_not_called()
        self.tool.assert_not_called()
        self.plan_model.assert_not_called()
        sink.assert_not_called()

    # 模型直接回答却没有工具证据时，不能进入付费的计划生成阶段。
    def test_no_evidence_stops_before_plan_request(self):
        sink = Mock()
        self.research_model.side_effect = [self.research_messages[-1]]
        with self.assertRaisesRegex(InsufficientPlanEvidenceError, "without code evidence"):
            self.run_agent(event_sink=sink)
        self.research_model.assert_called_once()
        self.tool.assert_not_called()
        self.plan_model.assert_not_called()
        self.assertEqual(self.plan_events(sink), [])

    # 非法计划必须经过真实解析器拒绝，并产生配对失败事件，不能发布 PLAN_CREATED。
    def test_invalid_plan_emits_failure(self):
        sink = Mock()
        invalid_content = "private invalid model output"
        self.plan_model.return_value = {"role": "assistant", "content": invalid_content}
        with self.assertRaises(InvalidPlanError):
            self.run_agent(event_sink=sink)
        self.plan_model.assert_called_once()
        events = self.plan_events(sink)
        self.assertEqual([event["event_type"] for event in events], [
            "MODEL_CALL_STARTED", "MODEL_CALL_FAILED",
        ])
        started, failed = [event["payload"] for event in events]
        self.assertEqual(failed["call_id"], started["call_id"])
        self.assertEqual(failed["attempt"], started["attempt"])
        self.assertEqual(failed["error_type"], "InvalidPlanError")
        self.assertGreaterEqual(failed["duration_ms"], 0)
        self.assertNotIn(invalid_content, json.dumps(events, ensure_ascii=False))

    # 开始、完成、计划发布任一事件写入失败时，不得向调用方报告计划生成成功。
    # MODEL_CALL_FAILED 的写入失败另有保留原始生成异常的策略，不属于此成功路径测试。
    def test_event_write_failures_are_propagated(self):
        event_order = ["MODEL_CALL_STARTED", "MODEL_CALL_COMPLETED", "PLAN_CREATED"]
        for failed_index, failed_type in enumerate(event_order):
            with self.subTest(event_type=failed_type):
                self.research_model.reset_mock()
                self.research_model.side_effect = self.research_messages
                self.tool.reset_mock()
                self.plan_model.reset_mock()
                event_error = RuntimeError(f"cannot persist {failed_type}")

                def record_event(**kwargs):
                    if kwargs["node_name"] == "plan" and kwargs["event_type"] == failed_type:
                        raise event_error

                sink = Mock(side_effect=record_event)
                with self.assertRaises(RuntimeError) as caught:
                    self.run_agent(event_sink=sink)
                self.assertIs(caught.exception, event_error)
                self.assertEqual(
                    [event["event_type"] for event in self.plan_events(sink)],
                    event_order[:failed_index + 1],
                )
                if failed_type == "MODEL_CALL_STARTED":
                    self.plan_model.assert_not_called()
                else:
                    self.plan_model.assert_called_once()


if __name__ == "__main__":
    unittest.main()
