import logging
import subprocess
from dataclasses import dataclass
from uuid import uuid4

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


# 输出截断助手
def _truncate_output(
    value: str,
    *,
    max_chars: int,
) -> tuple[str, bool]:
    if len(value) <= max_chars:
        return value, False

    return value[:max_chars], True


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

    # 6. subprocess.run 执行，不使用 shell=True。
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )

        stdout, stdout_truncated = _truncate_output(
            result.stdout,
            max_chars=max_output_chars
        )

        stderr, stderr_truncated = _truncate_output(
            result.stderr,
            max_chars=max_output_chars
        )

        return SandboxTestResult(
            exit_code=result.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )

    except subprocess.TimeoutExpired as exc:
        _force_remove_container(container_name)

        raw_stdout = exc.stdout or ""
        raw_stderr = exc.stderr or ""

        # TimeoutExpired 在某些 Python/平台组合下即使 text=True，
        # stdout/stderr 仍可能是 bytes。
        if isinstance(raw_stdout, bytes):
            raw_stdout = raw_stdout.decode(
                "utf-8",
                errors="replace",
            )

        if isinstance(raw_stderr, bytes):
            raw_stderr = raw_stderr.decode(
                "utf-8",
                errors="replace",
            )

        stdout, stdout_truncated = _truncate_output(
            raw_stdout,
            max_chars=max_output_chars
        )
        stderr, stderr_truncated = _truncate_output(
            raw_stderr,
            max_chars=max_output_chars
        )

        return SandboxTestResult(
            exit_code=None,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )

    except OSError as exc:
        raise SandboxExecutionError("Docker test runner could not be started") from exc
