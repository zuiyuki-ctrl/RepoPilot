import subprocess
from pathlib import Path

import pytest

from backend.app.core.exceptions import SandboxExecutionError
from backend.app.services import docker_test_service
from backend.app.services import sandbox_test_service
from backend.app.services.docker_test_service import SandboxTestResult
from backend.app.services.sandbox_snapshot_service import SandboxSnapshot


def make_snapshot(root: Path) -> SandboxSnapshot:
    return SandboxSnapshot(
        root=root,
        files=["example.py", "test_example.py"],
        total_bytes=1,
    )


def test_workspace_pytest_uses_snapshot_and_cleans_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "example.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    (workspace / "test_example.py").write_text(
        "from example import add\n\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_run_pytest_in_docker(
        snapshot: SandboxSnapshot,
        *,
        image: str,
        timeout_seconds: int,
        max_output_chars: int,
    ) -> SandboxTestResult:
        # TODO 1：
        # 验证调用 Docker 时临时快照仍然存在。
        # 保存 snapshot.root，供退出 with 后检查清理。
        assert snapshot.root.exists()
        assert snapshot.root.is_dir()
        assert (snapshot.root / "example.py").is_file()
        assert (snapshot.root / "test_example.py").is_file()
        captured["root"] = snapshot.root
        captured["files"] = snapshot.files
        captured["image"] = image
        captured["timeout_seconds"] = timeout_seconds
        captured["max_output_chars"] = max_output_chars

        return SandboxTestResult(
            exit_code=0,
            stdout="1 passed",
            stderr="",
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )

    monkeypatch.setattr(
        sandbox_test_service,
        "run_pytest_in_docker",
        fake_run_pytest_in_docker,
    )

    result = sandbox_test_service.run_workspace_pytest(workspace)

    # TODO 2：
    # 检查 result 表示测试成功。
    # 检查被复制的两个 Python 文件。
    # 检查函数返回后 captured 中的临时目录已不存在。
    assert result.exit_code == 0
    assert result.stdout == "1 passed"
    assert result.stderr == ""
    assert result.timed_out is False
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False
    assert captured["files"] == ["example.py", "test_example.py"]
    assert captured["image"] == docker_test_service.DEFAULT_TEST_IMAGE
    assert captured["timeout_seconds"] == docker_test_service.DEFAULT_TEST_TIMEOUT_SECONDS
    assert captured["max_output_chars"] == docker_test_service.MAX_TEST_OUTPUT_CHARS
    assert not captured["root"].exists()


def test_docker_runner_returns_pytest_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = make_snapshot(tmp_path)
    captured: dict[str, list[str]] = {}

    def fake_subprocess_run(command, **kwargs):
        # TODO 3：
        # 保存 command，随后模拟 pytest 断言失败。
        captured["command"] = command
        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout="1 failed",
            stderr="",
        )

    monkeypatch.setattr(
        docker_test_service.subprocess,
        "run",
        fake_subprocess_run,
    )

    result = docker_test_service.run_pytest_in_docker(snapshot)

    # TODO 4：
    # 验证 exit_code == 1，但没有抛 SandboxExecutionError。
    # 验证 timed_out 为 False。
    # 验证命令包含关键隔离参数：
    # --network none、--read-only、--cap-drop ALL。
    assert result.exit_code == 1
    assert result.stdout == "1 failed"
    assert result.stderr == ""
    assert result.timed_out is False
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False

    command = captured["command"]
    network_index = command.index("--network")
    cap_drop_index = command.index("--cap-drop")
    assert command[network_index + 1] == "none"
    assert "--read-only" in command
    assert command[cap_drop_index + 1] == "ALL"


def test_docker_runner_cleans_timed_out_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = make_snapshot(tmp_path)
    commands: list[list[str]] = []

    def fake_subprocess_run(command, **kwargs):
        commands.append(command)

        if command[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(
                cmd=command,
                timeout=1,
                output=b"partial stdout",
                stderr=b"partial stderr",
            )

        # docker rm --force 的模拟结果
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        docker_test_service.subprocess,
        "run",
        fake_subprocess_run,
    )

    result = docker_test_service.run_pytest_in_docker(snapshot)

    # TODO 5：
    # 检查 timed_out、exit_code 和解码后的输出。
    # 检查 commands 中先出现 docker run，
    # 随后出现 docker rm --force，并且两者容器名相同。
    assert result.timed_out is True
    assert result.exit_code is None
    assert result.stdout == "partial stdout"
    assert result.stderr == "partial stderr"
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False

    assert len(commands) == 2
    run_command, cleanup_command = commands
    assert run_command[:2] == ["docker", "run"]
    assert cleanup_command[:3] == ["docker", "rm", "--force"]
    container_name = run_command[run_command.index("--name") + 1]
    assert cleanup_command[3] == container_name


def test_docker_start_failure_becomes_domain_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = make_snapshot(tmp_path)

    def fake_subprocess_run(command, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(
        docker_test_service.subprocess,
        "run",
        fake_subprocess_run,
    )

    # TODO 6：
    # 使用 pytest.raises 验证抛出 SandboxExecutionError，
    # 同时验证 __cause__ 是 FileNotFoundError。
    with pytest.raises(SandboxExecutionError) as exc_info:
        docker_test_service.run_pytest_in_docker(snapshot)

    assert isinstance(exc_info.value.__cause__, FileNotFoundError)
