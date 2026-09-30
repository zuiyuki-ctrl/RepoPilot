import logging
import subprocess
from dataclasses import dataclass
from uuid import uuid4
from threading import Thread

from .process_output import CapturedOutput, drain_text_stream
from ..core.exceptions import SandboxExecutionError
from .repository_scanner import _is_link_or_reparse_point
from .sandbox_snapshot_service import SandboxSnapshot


DEFAULT_TEST_IMAGE = "repopilot-pytest:py311"
DEFAULT_TEST_TIMEOUT_SECONDS = 120
MAX_TEST_OUTPUT_CHARS = 50_000

logger = logging.getLogger(__name__)

# 定义测试结果
@dataclass(frozen=True)
class SandboxTestResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool


# 容器清理助手
def _force_remove_container(container_name: str) -> None:
    try:
        subprocess.run(
            [
                "docker",
                "rm",
                "--force",
                container_name,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning(
            "Failed to remove timed-out sandbox container",
            exc_info=True,
        )



def run_pytest_in_docker(
    snapshot: SandboxSnapshot,
    *,
    image: str = DEFAULT_TEST_IMAGE,
    timeout_seconds: int = DEFAULT_TEST_TIMEOUT_SECONDS,
    max_output_chars: int = MAX_TEST_OUTPUT_CHARS,
) -> SandboxTestResult:
    # 1. 校验 image 是非空白字符串。
    if not isinstance(image, str) or image.strip() == "":
        raise SandboxExecutionError()

    # 2. timeout_seconds 和 max_output_chars
    #    必须是非 bool 的正整数。
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or timeout_seconds <= 0
    ):
        raise SandboxExecutionError("timeout_seconds must be a positive integer")

    if (
        isinstance(max_output_chars, bool)
        or not isinstance(max_output_chars, int)
        or max_output_chars <= 0
    ):
        raise SandboxExecutionError("max_output_chars must be a positive integer")

    # 3. 严格解析 snapshot.root：
    #    必须存在、是目录，并与 snapshot.root.resolve() 一致使用。
    try:
        snapshot_root = snapshot.root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SandboxExecutionError("Sandbox snapshot is unavailable") from exc

    if not snapshot_root.is_dir():
        raise SandboxExecutionError("Sandbox snapshot must be a directory")

    if _is_link_or_reparse_point(snapshot.root):
        raise SandboxExecutionError("Sandbox snapshot root must not be a link or reparse point")

    # 4. 创建唯一容器名。
    container_name = f"repopilot-test-{uuid4().hex}"

    # 5. 构造固定 Docker 命令。
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,

        "--network",
        "none",

        "--read-only",

        "--cap-drop",
        "ALL",

        "--security-opt",
        "no-new-privileges",

        "--pids-limit",
        "128",

        "--memory",
        "512m",

        "--cpus",
        "1.0",

        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",

        "--mount",
        f"type=bind,source={snapshot_root},target=/workspace,readonly",

        "--workdir",
        "/workspace",

        "--env",
        "PYTHONDONTWRITEBYTECODE=1",

        image,

        "python",
        "-m",
        "pytest",
        "-q",
        "--disable-warnings",
        "--maxfail=20",
        "-p",
        "no:cacheprovider",
    ]

    # 6. subprocess.Popen 执行，不使用 shell=True。
    return _run_docker_process(
        command,
        container_name=container_name,
        timeout_seconds=timeout_seconds,
        max_output_chars=max_output_chars,
    )


def _run_docker_process(
    command: list[str],
    *,
    container_name: str,
    timeout_seconds: int,
    max_output_chars: int,
) -> SandboxTestResult:
    stdout_capture = CapturedOutput()
    stderr_capture = CapturedOutput()

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise SandboxExecutionError("Docker test runner could not be started") from exc

    # Popen 配置了 PIPE，正常情况下两者不会是 None。
    # 显式检查能避免把类型断言当成运行时保证。
    if process.stdout is None or process.stderr is None:
        process.kill()
        process.wait()

        raise SandboxExecutionError("Docker test runner output pipes are unavailable")

    stdout_thread = Thread(
        target=drain_text_stream,
        kwargs={
            "stream": process.stdout,
            "captured": stdout_capture,
            "max_chars": max_output_chars,
        },
        name=f"{container_name}-stdout",
    )
    stderr_thread = Thread(
        target=drain_text_stream,
        kwargs={
            "stream": process.stderr,
            "captured": stderr_capture,
            "max_chars": max_output_chars,
        },
        name=f"{container_name}-stderr",
    )

    # 启动两个读取线程。
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False

    try:
        # 等待 Docker CLI 结束。
        # 主线程暂停执行，等待 OS 里的这个 process 进程结束
        process.wait(timeout=timeout_seconds)

    except subprocess.TimeoutExpired:
        timed_out = True

        # 先删除有唯一名称的容器。
        _force_remove_container(container_name)

        # 如果 Docker CLI 仍未退出，终止本地进程并回收。
        # 可以先 process.kill()，再 process.wait()。
        process.kill()
        process.wait()

    finally:
        # 必须等待两个排空线程结束。
        # 此时子进程已退出，管道最终会到达 EOF。
        stdout_thread.join()
        stderr_thread.join()

    # 如果任一 capture.error 不为 None，
    # 抛 SandboxExecutionError，并用 raise ... from
    # 保留最先发现的读取异常。
    stream_error = stdout_capture.error or stderr_capture.error

    if stream_error is not None:
        raise SandboxExecutionError("Cannot read Docker test output") from stream_error


    stdout = stdout_capture.get_text()
    stderr = stderr_capture.get_text()

    if timed_out:
        return SandboxTestResult(
            exit_code=None,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            stdout_truncated=stdout_capture.truncated,
            stderr_truncated=stderr_capture.truncated,
        )

    return_code = process.returncode

    if return_code in {125, 126, 127}:
        raise SandboxExecutionError(
            f"Docker test command could not run; "
            f"exit_code={return_code}"
        )

    return SandboxTestResult(
        exit_code=return_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
        stdout_truncated=stdout_capture.truncated,
        stderr_truncated=stderr_capture.truncated,
    )