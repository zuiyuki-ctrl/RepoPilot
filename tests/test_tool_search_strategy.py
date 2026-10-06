import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from pydantic import ValidationError

from backend.app.services import tool_service as service


class ToolSearchStrategyTests(unittest.TestCase):
    def setUp(self):
        self.repository_id = UUID(int=1)
        self.searches = {
            strategy: self.enterContext(patch.object(service, name))
            for strategy, name in (
                ("vector", "semantic_search"), ("keyword", "keyword_search"),
                ("hybrid", "hybrid_search_with_diagnostics"))
        }

    def execute(self, **arguments):
        return service.execute_readonly_tool(self.repository_id, tool_name="search_code", arguments=arguments)

    def test_old_arguments_default_to_vector(self):
        self.searches["vector"].return_value = []
        self.assertEqual(self.execute(query="哪里校验仓库路径"),
                         dict(strategy="vector", hits=[], diagnostics=None))
        self.searches["vector"].assert_called_once_with(self.repository_id, query="哪里校验仓库路径", top_k=5)
        self.searches["keyword"].assert_not_called()
        self.searches["hybrid"].assert_not_called()

    def test_dispatch_preserves_scores_and_serializes_diagnostics(self):
        for strategy, score in (("vector", {"distance": 0.2}), ("keyword", {"score": 0.8}),
                                ("hybrid", {"rrf_score": 0.03, "vector_rank": 1, "keyword_rank": 2})):
            with self.subTest(strategy=strategy):
                for search in self.searches.values():
                    search.reset_mock()
                serialized = {"chunk": {"file_path": "example.py"}, **score}
                hit = Mock()
                hit.model_dump.return_value = serialized
                diagnostics = Mock()
                diagnostics.model_dump.return_value = {"overlap_count": 1}
                self.searches[strategy].return_value = (
                    SimpleNamespace(hits=[hit], diagnostics=diagnostics) if strategy == "hybrid" else [hit])
                result = self.execute(query="validate_source_path", strategy=strategy, top_k=3)
                self.assertEqual(result, dict(strategy=strategy, hits=[serialized],
                    diagnostics={"overlap_count": 1} if strategy == "hybrid" else None))
                hit.model_dump.assert_called_once_with(mode="json")
                if strategy == "hybrid":
                    diagnostics.model_dump.assert_called_once_with(mode="json")
                for name, search in self.searches.items():
                    if name == strategy:
                        search.assert_called_once_with(self.repository_id, query="validate_source_path", top_k=3)
                    else:
                        search.assert_not_called()

    def test_missing_repository_and_empty_hits_are_distinct(self):
        for strategy, search in self.searches.items():
            with self.subTest(strategy=strategy):
                search.return_value = None
                with self.assertRaisesRegex(ValueError, "^Repository not found$"):
                    self.execute(query="example", strategy=strategy)
                diagnostics = Mock()
                diagnostics.model_dump.return_value = {}
                search.return_value = SimpleNamespace(hits=[], diagnostics=diagnostics) if strategy == "hybrid" else []
                self.assertEqual(self.execute(query="example", strategy=strategy)["hits"], [])

    def test_invalid_arguments_never_reach_retrieval(self):
        for extra in ({"strategy": "unknown"}, {"strategy": None}, {"top_k": 6},
                      {"top_k": "3"}, {"top_k": True}, {"repository_id": str(UUID(int=2))}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                self.execute(query="example", **extra)
        for search in self.searches.values():
            search.assert_not_called()
