from pathlib import Path
from tempfile import TemporaryDirectory

from .docker_test_service import (
    DEFAULT_TEST_IMAGE,
    DEFAULT_TEST_TIMEOUT_SECONDS,
    MAX_TEST_OUTPUT_CHARS,
    SandboxTestResult,
    run_pytest_in_docker,
)
from .sandbox_snapshot_service import prepare_python_test_snapshot


"""
创建工作副本的隔离快照，在 Docker 中执行 pytest，
并在执行结束后自动清理临时快照。
"""
# 直接测试一个工作副本：创建临时快照、调用 Docker pytest，退出时清理快照。
# 这是不关联任务状态和事件的测试入口；任务流程由 task_test_service 协调。
def run_workspace_pytest(
    workspace_path: Path,
    *,
    image: str = DEFAULT_TEST_IMAGE,
    timeout_seconds: int = DEFAULT_TEST_TIMEOUT_SECONDS,
    max_output_chars: int = MAX_TEST_OUTPUT_CHARS,
) -> SandboxTestResult:

    # 使用 TemporaryDirectory 创建专属于本次测试的临时目录。
    # prefix 使用 "repopilot-pytest-"。
    #
    # TemporaryDirectory 返回的是字符串路径，
    # 需要通过 Path(...) 转换后再传给快照服务。
    with TemporaryDirectory(prefix="repopilot-pytest-") as temporary_directory:
        snapshot_path = Path(temporary_directory)

        # 从 workspace_path 准备 Python 测试快照。
        snapshot = prepare_python_test_snapshot(workspace_path, snapshot_path)

        # 把 snapshot 和三个运行参数交给 run_pytest_in_docker。
        # 必须 return 它的 SandboxTestResult。
        return run_pytest_in_docker(
            snapshot,
            image=image,
            timeout_seconds=timeout_seconds,
            max_output_chars=max_output_chars,
        )