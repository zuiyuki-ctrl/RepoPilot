import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.core.exceptions import InvalidWorkspacePathError
from backend.app.services.workspace_edit_service import resolve_workspace_target


class ResolveWorkspaceTargetTests(unittest.TestCase):
    def test_existing_file_is_resolved(self):
        # 在临时 workspace 中创建 app/main.py。
        with TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            target = workspace / "app" / "main.py"
            target.parent.mkdir(parents=True)
            target.write_text("print('hello')\n", encoding="utf-8")

            result = resolve_workspace_target(workspace, "app/main.py")

            # 断言返回该文件的绝对 Path。
            self.assertIsInstance(result, Path)
            self.assertTrue(result.is_absolute())
            self.assertEqual(result, target.resolve())

    def test_new_file_is_resolved(self):
        # 父目录存在，但目标文件尚不存在。
        with TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            parent = workspace / "app"
            parent.mkdir(parents=True)
            target = parent / "new.py"
            self.assertFalse(target.exists())

            result = resolve_workspace_target(workspace, "app/new.py")

            # 断言仍返回 workspace 内的目标 Path。
            self.assertEqual(result, target.resolve())
            self.assertTrue(result.is_absolute())
            self.assertFalse(result.exists())

    def test_invalid_relative_paths_are_rejected(self):
        # 用 subTest 覆盖路径穿越、绝对路径和不规范路径段。
        invalid_paths = (
            "../x.py",
            "/x.py",
            "C:/x.py",
            "a\\b.py",
            "a//b.py",
            "a/./b.py",
            " x.py",
        )

        with TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()

            for file_path in invalid_paths:
                with self.subTest(file_path=file_path):
                    with self.assertRaises(InvalidWorkspacePathError):
                        resolve_workspace_target(workspace, file_path)

    def test_link_component_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = temp_root / "workspace"
            outside = temp_root / "outside"
            workspace.mkdir()
            outside.mkdir()
            link = workspace / "link"

            # Windows 未启用开发者模式或没有相应权限时无法创建链接。
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"当前平台无法创建目录符号链接：{exc}")

            # workspace/link 指向 workspace 外部目录，必须拒绝。
            with self.assertRaises(InvalidWorkspacePathError):
                resolve_workspace_target(workspace, "link/x.py")


if __name__ == "__main__":
    unittest.main()
