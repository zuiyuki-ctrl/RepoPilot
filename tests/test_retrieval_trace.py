from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from backend.app.agent import nodes
from backend.app.agent.context import AgentRunContext
from backend.app.agent.policy import BUDGET_ERROR
from backend.app.agent.retrieval_trace import text_hash, model_tool_context
from backend.app.schemas.run_config import AgentRunConfig


class RetrievalTraceTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.runtime = SimpleNamespace(
            context=AgentRunContext(event_sink=lambda **event: self.events.append(event)),
            execution_info=None,
        )
        self.tool = self.enterContext(patch.object(nodes, "execute_readonly_tool"))
        self.model = self.enterContext(patch.object(nodes, "request_tool_turn",
            return_value={"role": "assistant", "content": "回答 [S1]"}))

    def state(self, *, remaining=40000, names=("search_code",), max_calls=4):
        return dict(
            repository_id=UUID(int=1), max_tool_calls=max_calls, used_calls=0,
            remaining_chars=remaining, output_exhausted=False, allow_tools=True,
            sources=[], tool_trace=[], result=None,
            messages=[{"role": "system", "content": "test prompt"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": f"tool-{index}", "type": "function", "function": {
                        "name": name, "arguments": json.dumps({"query": " 中文 symbol ", "top_k": 2})}}
                    for index, name in enumerate(names)
                ]}],
        )

    def result(self, strategy="vector", content="def target():\n    return 1\n"):
        score = {
            "vector": {"distance": 0.1}, "keyword": {"score": 0.8},
            "hybrid": {"rrf_score": 0.03, "vector_rank": 1, "keyword_rank": 2,
                       "vector_distance": 0.1, "keyword_score": 0.8},
        }[strategy]
        return dict(requested_strategy="vector", strategy=strategy, diagnostics=None, hits=[
            {"chunk": dict(id=str(UUID(int=index)), file_id=str(UUID(int=10)),
                file_path="target.py", symbol_name="target", start_line=1, end_line=2,
                content=content), **score}
            for index in (2, 3)
        ])

    def payloads(self, event_type):
        return [e["payload"] for e in self.events if e["event_type"] == event_type]

    def test_ranked_returns_and_accepted_context_match_model_message(self):
        for strategy in ("vector", "keyword", "hybrid"):
            with self.subTest(strategy=strategy):
                self.events.clear()
                self.tool.reset_mock()
                result = self.result(strategy)
                original = deepcopy(result)
                self.tool.return_value = result
                state = self.state()
                update = nodes.tools_node(state, self.runtime)
                retrieved = self.payloads("RETRIEVAL_COMPLETED")[0]
                context = self.payloads("TOOL_CONTEXT_PREPARED")[0]
                self.assertEqual(retrieved["query"], " 中文 symbol ")
                self.assertEqual(retrieved["effective_query"], " 中文 symbol " if strategy == "vector" else "中文 symbol")
                self.assertEqual(retrieved["retrieval_strategy"], strategy)
                self.assertEqual([h["rank"] for h in retrieved["hits"]], [1, 2])
                self.assertEqual([h["chunk_id"] for h in retrieved["hits"]], [str(UUID(int=2)), str(UUID(int=3))])
                self.assertNotIn("content", retrieved["hits"][0])
                self.assertEqual(context["disposition"], "accepted")
                self.assertEqual([s["source_id"] for s in context["sources"]], ["S1", "S2"])
                self.assertEqual(context["call_id"], retrieved["call_id"])
                text = update["messages"][-1]["content"]
                self.assertEqual(context["content_sha256"], text_hash(text))
                self.assertEqual(context["content_chars"], len(text))
                self.assertEqual(context["remaining_chars_after"], 40000 - len(text))
                nodes.model_node({**state, **update}, self.runtime)
                request = self.payloads("MODEL_CALL_STARTED")[0]
                self.assertEqual(request["tool_context"], model_tool_context(self.model.call_args.args[0]))
                self.assertEqual(request["tool_context"][0]["content_sha256"], context["content_sha256"])
                self.assertEqual(result, original)
                self.tool.assert_called_once()

    def test_returned_hits_can_be_discarded_without_becoming_sources(self):
        self.tool.return_value = self.result(content="x" * 4000)
        state = self.state(remaining=200)
        update = nodes.tools_node(state, self.runtime)
        self.assertEqual(len(self.payloads("RETRIEVAL_COMPLETED")[0]["hits"]), 2)
        context = self.payloads("TOOL_CONTEXT_PREPARED")[0]
        self.assertEqual(context["disposition"], "discarded")
        self.assertEqual(context["sources"], [])
        self.assertEqual(update["sources"], [])
        self.assertEqual(context["content_sha256"], text_hash(json.dumps(BUDGET_ERROR, ensure_ascii=False)))
        self.assertGreater(context["prepared_result_chars"], context["content_chars"])
        nodes.model_node({**state, **update}, self.runtime)
        self.assertEqual(self.payloads("MODEL_CALL_STARTED")[0]["tool_context"][0]["content_sha256"],
                         context["content_sha256"])

    def test_empty_search_is_success_with_zero_sources(self):
        self.tool.return_value = dict(requested_strategy="vector", strategy="vector", hits=[], diagnostics=None)
        update = nodes.tools_node(self.state(), self.runtime)
        self.assertEqual(self.payloads("RETRIEVAL_COMPLETED")[0]["hits"], [])
        context = self.payloads("TOOL_CONTEXT_PREPARED")[0]
        self.assertEqual(context["disposition"], "accepted")
        self.assertFalse(context["has_error"])
        self.assertEqual(update["sources"], [])

    def test_skip_and_error_do_not_inherit_previous_retrieval(self):
        self.tool.side_effect = [self.result(), ValueError("invalid argument")]
        update = nodes.tools_node(self.state(names=("search_code",) * 3, max_calls=2), self.runtime)
        contexts = self.payloads("TOOL_CONTEXT_PREPARED")
        self.assertEqual([c["disposition"] for c in contexts], ["accepted", "tool_error", "skipped"])
        self.assertEqual([c["tool_message_index"] for c in contexts], [0, 1, 2])
        self.assertEqual(len(self.payloads("RETRIEVAL_COMPLETED")), 1)
        self.assertEqual(self.tool.call_count, 2)
        self.assertEqual(contexts[1]["sources"], [])
        self.assertEqual(contexts[2]["sources"], [])
        self.assertFalse(contexts[2]["attempted"])
        self.assertEqual(len(update["sources"]), 2)

    def test_read_source_keeps_file_hash_and_slice_hash_distinct(self):
        content = "print('中文')\n"
        self.tool.return_value = dict(file_path="target.py", file_hash="a" * 64,
                                      start_line=10, end_line=10, content=content)
        nodes.tools_node(self.state(names=("read_source",)), self.runtime)
        self.assertEqual(self.payloads("RETRIEVAL_COMPLETED"), [])
        source = self.payloads("TOOL_CONTEXT_PREPARED")[0]["sources"][0]
        self.assertEqual(source["file_hash"], "a" * 64)
        self.assertEqual(source["content_sha256"], text_hash(content))
        self.assertEqual(source["source_id"], "S1")

    def test_event_persistence_failure_stops_before_another_model_call(self):
        self.tool.return_value = self.result()
        def fail(**event):
            if event["event_type"] == "TOOL_CONTEXT_PREPARED":
                raise RuntimeError("persistence failed")
        runtime = SimpleNamespace(context=AgentRunContext(event_sink=fail), execution_info=None)
        with self.assertRaisesRegex(RuntimeError, "persistence failed"):
            nodes.tools_node(self.state(), runtime)
        self.model.assert_not_called()

    def test_duplicate_tool_ids_keep_order_and_distinct_message_hashes(self):
        refs = model_tool_context([
            {"role": "tool", "tool_call_id": "same", "content": "first"},
            {"role": "assistant", "content": "not a tool"},
            {"role": "tool", "tool_call_id": "same", "content": "second"},
        ])
        self.assertEqual([r["tool_message_index"] for r in refs], [0, 1])
        self.assertNotEqual(refs[0]["content_sha256"], refs[1]["content_sha256"])

    def test_model_failure_keeps_attempt_evidence_without_claiming_success(self):
        self.model.side_effect = TimeoutError("network timeout")
        state = self.state()
        state["messages"].append({"role": "tool", "tool_call_id": "tool-0", "content": "{}"})
        with self.assertRaises(TimeoutError):
            nodes.model_node(state, self.runtime)
        self.assertEqual(len(self.payloads("MODEL_CALL_STARTED")[0]["tool_context"]), 1)
        self.assertEqual(self.payloads("MODEL_CALL_COMPLETED"), [])
        self.assertEqual(len(self.payloads("MODEL_CALL_FAILED")), 1)
