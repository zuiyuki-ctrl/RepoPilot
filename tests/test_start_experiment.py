import io
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.app.schemas.experiment import ExperimentCase, ExperimentPreparation
from scripts import start_experiment as script


class StartExperimentTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.case = ExperimentCase(
            case_id="sample", case_version="v1", task_type="bug_fix",
            user_request="修复示例", repository_commit="a" * 40,
            editable_files=["example.py"], protected_test_files=["tests/test_example.py"],
            test_profile="python-basic",
        )
        self.summary = dict(source_path=str(self.root / "source"),
                            protected_test_file_hashes={"tests/test_example.py": "hash"})
        self.repository = SimpleNamespace(id=uuid4(), workspace_path=str(self.root / "copy"),
                                          commit_hash=self.case.repository_commit)
        self.inspect = self.enterContext(patch.object(script, "inspect_experiment_source", return_value=self.summary))
        self.create = self.enterContext(patch.object(script, "create_repository", return_value=self.repository))
        self.profile = self.enterContext(patch.object(script, "update_repository_test_profile", return_value=self.repository))
        self.index = self.enterContext(patch.object(script, "index_repository_chunks",
            return_value=SimpleNamespace(chunk_count=1, skipped_files=[])))
        self.embed = self.enterContext(patch.object(script, "embed_repository_chunks", return_value=0))
        self.task = self.enterContext(patch.object(script, "create_task", side_effect=lambda data:
            SimpleNamespace(id=uuid4(), repository_id=data.repository_id,
                            status="created", run_config=data.run_config)))

    def prepare(self, policy="vector"):
        return script.prepare_experiment_run(self.case, source_path=self.root / "source",
            retrieval_policy=policy, output_dir=self.root / "output")

    def saved(self):
        paths = list((self.root / "output").glob("*/preparation.json"))
        self.assertEqual(len(paths), 1)
        return ExperimentPreparation.model_validate_json(paths[0].read_text(encoding="utf-8"))

    def test_success_with_zero_embeddings_and_independent_runs(self):
        second_repository = SimpleNamespace(
            id=uuid4(), workspace_path=str(self.root / "copy-hybrid"),
            commit_hash=self.case.repository_commit,
        )
        self.create.side_effect = [self.repository, second_repository]
        first = self.prepare()
        self.assertEqual(first.status, "prepared")
        self.assertEqual(self.saved(), first)
        self.assertEqual(first.run_config.max_tool_calls, 4)
        self.assertEqual(self.task.call_args.args[0].task_type, "plan")
        second = self.prepare("hybrid")
        self.assertNotEqual(first.experiment_id, second.experiment_id)
        self.assertNotEqual(first.repository_id, second.repository_id)
        self.assertNotEqual(first.workspace_path, second.workspace_path)
        self.assertEqual(first.repository_id, self.repository.id)
        self.assertEqual(first.workspace_path, self.repository.workspace_path)
        self.assertEqual(second.repository_id, second_repository.id)
        self.assertEqual(second.workspace_path, second_repository.workspace_path)
        self.assertEqual(first.run_config.retrieval_policy, "vector")
        self.assertEqual(second.run_config.retrieval_policy, "hybrid")
        self.assertEqual(self.task.call_count, 2)
        self.assertEqual(self.task.call_args_list[0].args[0].repository_id, self.repository.id)
        self.assertEqual(self.task.call_args_list[1].args[0].repository_id, second_repository.id)
        self.assertEqual(self.create.call_count, 2)
        self.assertEqual(self.create.call_args.args[0].source_path, self.summary["source_path"])

    def test_source_failure_creates_nothing(self):
        self.inspect.side_effect = ValueError("bad source")
        with self.assertRaises(ValueError):
            self.prepare()
        self.create.assert_not_called()
        self.assertFalse((self.root / "output").exists())

    def test_incomplete_index_stops_before_embedding(self):
        for result in (None, SimpleNamespace(chunk_count=0, skipped_files=[]),
                       SimpleNamespace(chunk_count=1, skipped_files=["bad.py"])):
            with self.subTest(result=result), TemporaryDirectory() as directory:
                self.index.return_value = result
                with redirect_stderr(io.StringIO()), self.assertRaises(ValueError):
                    script.prepare_experiment_run(self.case, source_path=self.root / "source",
                        retrieval_policy="vector", output_dir=Path(directory))
        self.embed.assert_not_called()
        self.task.assert_not_called()

    def test_workspace_hash_mismatch_stops_before_profile(self):
        self.inspect.side_effect = [self.summary, {**self.summary, "protected_test_file_hashes": {}}]
        with redirect_stderr(io.StringIO()), self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.saved().stage, "inspect_workspace")
        self.profile.assert_not_called()

    def test_embedding_failure_retains_ids_and_original_error_when_save_fails(self):
        original = TimeoutError("timeout")
        self.embed.side_effect = original
        real_save = script.save_preparation

        def save(record, **kwargs):
            if record.status == "error":
                raise OSError("disk failure")
            real_save(record, **kwargs)

        stderr = io.StringIO()
        with patch.object(script, "save_preparation", side_effect=save), redirect_stderr(stderr):
            with self.assertRaises(TimeoutError) as raised:
                self.prepare()
        self.assertIs(raised.exception, original)
        self.assertIn(str(self.repository.id), stderr.getvalue())
        self.assertIn("stage=embedding", stderr.getvalue())
        self.assertIn("错误记录保存失败", stderr.getvalue())
        self.assertEqual(self.saved().repository_id, self.repository.id)
        self.task.assert_not_called()

    def test_embedding_none_records_error(self):
        self.embed.return_value = None
        with redirect_stderr(io.StringIO()), self.assertRaises(ValueError):
            self.prepare()
        record = self.saved()
        self.assertEqual((record.status, record.stage, record.error_type), ("error", "embedding", "ValueError"))

    def test_repository_response_checks_retain_repository_id(self):
        for changes in ({"commit_hash": "b" * 40}, {"workspace_path": None},
                        {"workspace_path": self.summary["source_path"]}):
            with self.subTest(changes=changes), TemporaryDirectory() as directory:
                self.create.return_value = SimpleNamespace(**{**vars(self.repository), **changes})
                with redirect_stderr(io.StringIO()), self.assertRaises(ValueError):
                    script.prepare_experiment_run(self.case, source_path=self.root / "source",
                        retrieval_policy="vector", output_dir=Path(directory))
                path = next(Path(directory).glob("*/preparation.json"))
                record = ExperimentPreparation.model_validate_json(path.read_text(encoding="utf-8"))
                self.assertEqual(record.repository_id, self.repository.id)
                self.assertEqual(record.stage, "register_repository")
        self.profile.assert_not_called()

    def test_invalid_task_responses_are_not_prepared(self):
        for changes in ({"repository_id": uuid4()}, {"status": "running"}, {"run_config": None}):
            with self.subTest(changes=changes), TemporaryDirectory() as directory:
                task_id = uuid4()
                self.task.side_effect = lambda data: SimpleNamespace(**{
                    **dict(id=task_id, repository_id=data.repository_id, status="created",
                           run_config=data.run_config), **changes})
                with redirect_stderr(io.StringIO()), self.assertRaises(ValueError):
                    script.prepare_experiment_run(self.case, source_path=self.root / "source",
                        retrieval_policy="vector", output_dir=Path(directory))
                path = next(Path(directory).glob("*/preparation.json"))
                record = ExperimentPreparation.model_validate_json(path.read_text(encoding="utf-8"))
                self.assertEqual((record.status, record.stage, record.task_id), ("error", "create_task", task_id))

    def test_atomic_replace_failure_preserves_previous_json(self):
        record = self.prepare()
        path = self.root / "output" / str(record.experiment_id) / "preparation.json"
        before = path.read_bytes()
        with patch.object(script.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                script.save_preparation(record.model_copy(update={"stage": "changed"}), output_path=path)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_cli_requires_embedding_permission_before_preparation(self):
        with patch.object(script.sys, "argv", ["start_experiment", "--case", "case.json",
                "--source-path", "source", "--retrieval-policy", "vector"]), \
                patch.object(script, "prepare_experiment_run") as prepare, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                script.main()
        self.assertEqual(raised.exception.code, 2)
        prepare.assert_not_called()
        self.create.assert_not_called()
