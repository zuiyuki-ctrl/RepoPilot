import json
import unittest
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from backend.app.agent.planning import parse_change_plan
from backend.app.core.exceptions import InvalidPlanError
from backend.app.schemas.agent import AgentSourceReference
from backend.app.schemas.plan import ChangePlan


# 直接测试计划解析器；不连接数据库、不调用模型、不创建或修改源码文件。
class ChangePlanTests(unittest.TestCase):
    def setUp(self):
        self.sources = [
            AgentSourceReference(source_id="S1", file_path="backend/app/example.py", start_line=1, end_line=10),
            AgentSourceReference(source_id="S2", file_path="tests/test_example.py", start_line=1, end_line=20),
        ]
        self.payload = {
            "summary": "调整实现并补充测试",
            "steps": [
                {
                    "id": 1,
                    "description": "修改实现",
                    "files": ["backend/app/example.py"],
                    "source_ids": ["S1"],
                    "verification": "检查返回结果符合预期",
                },
                {
                    "id": 2,
                    "description": "补充边界测试",
                    "files": ["tests/test_example.py"],
                    "source_ids": ["S2"],
                    "verification": "运行单元测试并确认通过",
                },
            ],
        }

    def parse(self, payload):
        return parse_change_plan(json.dumps(payload, ensure_ascii=False), sources=self.sources)

    # 每步可以只引用现有证据的一部分，不要求引用所有证据。
    def test_valid_json_returns_change_plan(self):
        result = self.parse(self.payload)
        self.assertIsInstance(result, ChangePlan)
        self.assertEqual(result.model_dump(), self.payload)

    def test_non_json_is_rejected(self):
        for content in ("这不是 JSON", "{", "```json\n{}\n```", ""):
            with self.subTest(content=content):
                with self.assertRaises(InvalidPlanError):
                    parse_change_plan(content, sources=self.sources)

    # 计划本身和嵌套步骤都必须拒绝模型额外生成的字段。
    def test_extra_fields_are_rejected(self):
        for location in ("plan", "step"):
            with self.subTest(location=location):
                payload = deepcopy(self.payload)
                target = payload if location == "plan" else payload["steps"][0]
                target["unexpected"] = "extra value"
                with self.assertRaisesRegex(InvalidPlanError, "JSON 结构"):
                    self.parse(payload)

    def test_empty_steps_are_rejected(self):
        self.payload["steps"] = []
        with self.assertRaises(InvalidPlanError):
            self.parse(self.payload)

    def test_invalid_step_numbering_is_rejected(self):
        for ids in ([2, 3], [1, 1], [1, 3], [2, 1]):
            with self.subTest(ids=ids):
                payload = deepcopy(self.payload)
                for step, step_id in zip(payload["steps"], ids):
                    step["id"] = step_id
                with self.assertRaisesRegex(InvalidPlanError, "步骤编号"):
                    self.parse(payload)

    # 同时检查混入未知编号和完全替换为未知编号，避免只比较集合长度造成漏检。
    def test_unknown_source_is_rejected(self):
        for source_ids in (["S9"], ["S1", "S9"]):
            with self.subTest(source_ids=source_ids):
                payload = deepcopy(self.payload)
                payload["steps"][0]["source_ids"] = source_ids
                with self.assertRaisesRegex(InvalidPlanError, "不存在的证据"):
                    self.parse(payload)

    def test_duplicate_source_ids_are_rejected(self):
        self.payload["steps"][0]["source_ids"] = ["S1", "S1", "S2"]
        with self.assertRaisesRegex(InvalidPlanError, "重复证据编号"):
            self.parse(self.payload)

    def test_invalid_file_paths_are_rejected(self):
        for file_path in ("../secret.py", "D:/secret.py", "", "   "):
            with self.subTest(file_path=file_path):
                payload = deepcopy(self.payload)
                payload["steps"][0]["files"] = [file_path]
                with self.assertRaises(InvalidPlanError):
                    self.parse(payload)

    # 修改计划允许提出新文件；路径合法性不能依赖该文件已经存在于磁盘或证据列表。
    def test_new_relative_file_path_is_allowed(self):
        new_file = f"backend/app/planned_{uuid4().hex}/new_feature.py"
        self.assertFalse(Path(new_file).exists())
        self.payload["steps"][0]["files"] = [new_file]
        result = self.parse(self.payload)
        self.assertIsInstance(result, ChangePlan)
        self.assertEqual(result.steps[0].files, [new_file])
        self.assertFalse(Path(new_file).exists())


if __name__ == "__main__":
    unittest.main()
