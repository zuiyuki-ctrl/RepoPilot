from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID
import logging
from dataclasses import dataclass

from sqlalchemy.exc import DBAPIError

from .sandbox_snapshot_service import SandboxSnapshot, prepare_python_test_snapshot
from ..core.exceptions import (
    TaskExecutionError,
    TaskStateConflictError, RepositoryBusyError,
)
from ..db.session import SessionLocal
from .docker_test_service import (
    DEFAULT_TEST_IMAGE,
    DEFAULT_TEST_TIMEOUT_SECONDS,
    MAX_TEST_OUTPUT_CHARS,
    SandboxTestResult, run_pytest_in_docker,
)

from ..db.repositories import (
    repository_repo,
    task_event_repo,
    task_repo,
    test_run_repo
)

logger = logging.getLogger(__name__)

# 只保存脱离 ORM 会话后仍然安全使用的数据
@dataclass(frozen=True)
class TaskTestContext:
    task_id: UUID
    repository_id: UUID
    workspace_path: Path
    test_run_id: UUID


# 协调任务测试：领取测试权、复制工作副本快照、在 Docker 中运行 pytest，最后保存测试结果。
# 快照准备或运行抛异常时尝试记录失败事件；临时快照由上下文管理器清理。
def run_task_pytest(
    task_id: UUID,
    *,
    image: str = DEFAULT_TEST_IMAGE,
    timeout_seconds: int = DEFAULT_TEST_TIMEOUT_SECONDS,
    max_output_chars: int = MAX_TEST_OUTPUT_CHARS,
) -> SandboxTestResult | None:
    """
    原子领取任务测试权，在数据库事务外运行 Docker，
    最后记录测试结果并恢复任务状态。
    """

    context = _begin_task_pytest(
        task_id,
        image=image,
        timeout_seconds=timeout_seconds,
    )

    if context is None:
        return None

    try:
        with TemporaryDirectory(prefix="repopilot-pytest-") as temporary_directory:
            # 1. 调用 _prepare_task_test_snapshot。
            #    传 context 和 Path(temporary_directory)。
            #    返回时，数据库事务已结束，仓库锁已释放。
            snapshot = _prepare_task_test_snapshot(context, Path(temporary_directory))

            _record_task_test_snapshot(
                context,
                snapshot_hash=snapshot.snapshot_hash,
            )
            # 2. 调用 run_pytest_in_docker。
            #    传入 snapshot、image、timeout_seconds、max_output_chars。
            #    把返回值保存为 result。
            result = run_pytest_in_docker(
                snapshot,
                image=image,
                timeout_seconds=timeout_seconds,
                max_output_chars=max_output_chars,
            )

    except Exception as exc:

        logger.exception(
            "Sandbox test execution failed; task_id=%s; test_run_id=%s",
            context.task_id,
            context.test_run_id,
        )
        # 调用 _fail_task_pytest 恢复状态，然后用裸 raise
        # 重新抛出最初的异常。
        try:
            _fail_task_pytest(context, exc)
        except Exception:
            logger.exception(
                "Failed to restore task after sandbox execution failure; "
                "task_id=%s",
                task_id,
            )
        raise

    # 正常执行完成时记录结果。
    _finish_task_pytest(context, result)

    return result


# 在短事务内锁定已批准且 executing 的计划任务，切换为 testing 并记录测试开始事件。
# 返回任务与工作副本信息，让后续耗时操作使用普通数据，不携带数据库对象。
def _begin_task_pytest(
    task_id: UUID,
    *,
    image: str,
    timeout_seconds: int,
) -> TaskTestContext | None:
    with SessionLocal.begin() as session:
        # 使用 get_task_for_update，而不是 get_task。
        # 行锁保证同一时刻只有一个请求能检查和修改状态。
        task = task_repo.get_task_for_update(session, task_id)

        if task is None:
            return None

        # 检查 plan、executing、approved 三个条件。
        if not (
            task.task_type == "plan"
            and task.status == "executing"
            and task.review_decision == "approved"
        ):
            raise TaskStateConflictError("Task is not ready for sandbox testing")

        # 查询关联 Repository，并检查 workspace_path。
        repository = repository_repo.get_repository(session, task.repository_id)

        if repository is None or not repository.workspace_path:
            raise TaskExecutionError("Task workspace is unavailable")

        test_run = test_run_repo.create_test_run(
            session,
            task_id=task_id,
            image=image,
            timeout_seconds=timeout_seconds,
        )

        if test_run is None:
            raise TaskExecutionError

        if test_run.status != "running":
            raise TaskStateConflictError

        # 调用 task_repo.mark_task_testing。
        task_repo.mark_task_testing(session, task)

        # 追加 TEST_EXECUTION_STARTED 事件。
        task_event_repo.append_task_event(
            session,
            task_id=task_id,
            event_type="TEST_EXECUTION_STARTED",
            node_name="task_test_service",
            message="Sandbox test execution started",
            payload={
                "step_id": "run_tests",
                "attempt": 1,
                "test_run_id": str(test_run.id),
            },
        )

        # 在会话内提取普通值并构造上下文。
        context = TaskTestContext(
            task_id=task_id,
            repository_id=repository.id,
            workspace_path=Path(repository.workspace_path),
            test_run_id=test_run.id,
        )

    return context


# 确认任务仍在 testing 且工作副本未变，再锁定仓库并复制测试快照。
# 仓库锁只覆盖复制阶段，退出事务后再运行 Docker，避免整个测试期间占用锁。
def _prepare_task_test_snapshot(
    context: TaskTestContext,
    snapshot_path: Path,
) -> SandboxSnapshot:
    # 1. 开启 SessionLocal.begin() 事务。
    with SessionLocal.begin() as session:
        # 2. 锁定 context.task_id 对应的任务。
        #    不存在：TaskExecutionError。
        #    要求 plan、testing、review_decision == "approved"。
        #    不符合：TaskStateConflictError。
        task = task_repo.get_task_for_update(session, context.task_id)
        if task is None:
            raise TaskExecutionError("Task disappeared during sandbox testing")

        if (
            task.task_type != "plan"
            or task.status != "testing"
            or task.review_decision != "approved"
        ):
            raise TaskStateConflictError()

        # 3. 检查 task.repository_id == context.repository_id。
        #    不一致：TaskExecutionError。
        if task.repository_id != context.repository_id:
            raise TaskExecutionError()

        # 4. 锁定仓库，具体处理见下文。
        try:
            repository = repository_repo.get_repository_for_update(session, task.repository_id)
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "55P03":
                raise RepositoryBusyError("Repository is busy") from exc
            raise

        # 5. 检查仓库存在、workspace_path 非空，
        #    并与 context.workspace_path 一致。
        if repository is None or not repository.workspace_path:
            raise TaskExecutionError("Task workspace is unavailable")

        if Path(repository.workspace_path) != context.workspace_path:
            raise TaskExecutionError()

        # 6. 在事务内部调用 prepare_python_test_snapshot。
        #    将结果保存到 snapshot。
        snapshot = prepare_python_test_snapshot(Path(repository.workspace_path), snapshot_path)

    # 7. 退出事务后，返回 snapshot。
    return snapshot


# 保存一次完整的测试结果和输出，记录 TEST_EXECUTION_FINISHED，并将任务恢复为 executing。
# 未超时且退出码为 0 才算通过；测试通过也不会在这里直接完成整个任务。
def _finish_task_pytest(
    context: TaskTestContext,
    result: SandboxTestResult,
) -> None:
    with SessionLocal.begin() as session:
        # 锁定任务；任务不存在时抛 TaskExecutionError。
        task = task_repo.get_task_for_update(session, context.task_id)

        if task is None:
            raise TaskExecutionError("Task disappeared during sandbox testing")

        # 只有 testing 状态可以结束本轮测试。
        if task.status != "testing":
            raise TaskStateConflictError("Task is no longer running sandbox tests")

        test_run = test_run_repo.get_test_run(
            session,
            task_id=context.task_id,
            test_run_id=context.test_run_id,
        )

        if test_run is None:
            raise TaskExecutionError

        if test_run.status != "running":
            raise TaskStateConflictError

        test_run_repo.finish_test_run(
            session,
            test_run=test_run,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            stdout=result.stdout,
            stderr=result.stderr,
            stderr_truncated=result.stderr_truncated,
            stdout_truncated=result.stdout_truncated
        )

        # 测试完成后先恢复到 executing。
        # 测试失败时，后续 Reflection 仍需继续修改工作区。
        task_repo.mark_task_executing(session, task)

        # 计算是否通过：
        # 未超时，并且退出码严格等于 0。
        passed = not result.timed_out and result.exit_code == 0

        # 追加 TEST_EXECUTION_FINISHED 事件。
        task_event_repo.append_task_event(
            session,
            task_id=task.id,
            event_type="TEST_EXECUTION_FINISHED",
            node_name="task_test_service",
            message=(
                "Sandbox tests passed"
                if passed
                else "Sandbox tests failed"
            ),
            payload={
                "step_id": "run_tests",
                "attempt": 1,
                "passed": passed,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "stdout_truncated": result.stdout_truncated,
                "stderr_truncated": result.stderr_truncated,
                "test_run_id": str(test_run.id),
            },
        )


# 准备快照或运行测试抛异常后，将 testing 任务恢复为 executing 并记录 TEST_EXECUTION_FAILED。
# 它记录执行流程异常；pytest 正常结束但断言失败，由完整结果事件记录。
def _fail_task_pytest(
    context: TaskTestContext,
    error: Exception,
) -> None:
    with SessionLocal.begin() as session:
        # 锁定任务。
        task = task_repo.get_task_for_update(session, context.task_id)

        if task is None:
            raise TaskExecutionError("Task disappeared during sandbox testing")

        # 必须仍处于 testing，否则不能覆盖其他流程写入的状态。
        if task.status != "testing":
            raise TaskStateConflictError("Task is no longer running sandbox tests")

        test_run = test_run_repo.get_test_run(
            session,
            task_id=context.task_id,
            test_run_id=context.test_run_id,
        )

        if test_run is None:
            raise TaskExecutionError

        if test_run.status != "running":
            raise TaskStateConflictError

        error_message = "Sandbox test execution failed; see server logs."

        test_run_repo.fail_test_run(
            session,
            test_run,
            error=error_message,
        )

        # 恢复到 executing，让用户可以修复环境或重新测试
        task_repo.mark_task_executing(session, task)

        # 记录基础设施执行失败。
        # 不保存 traceback，只保存受控的异常类型和简短消息。
        task_event_repo.append_task_event(
            session,
            task_id=task.id,
            event_type="TEST_EXECUTION_FAILED",
            node_name="task_test_service",
            message="Sandbox test execution failed",
            payload={
                "step_id": "run_tests",
                "attempt": 1,
                "error_type": type(error).__name__,
                "error": error_message,
                "test_run_id": str(test_run.id)
            },
        )


def _record_task_test_snapshot(
    context: TaskTestContext,
    *,
    snapshot_hash: str,
) -> None:
    with SessionLocal.begin() as session:
        # 1. 使用 get_task_for_update 锁定任务。
        task = task_repo.get_task_for_update(session, context.task_id)

        # 2. 任务不存在时抛 TaskExecutionError。
        if task is None:
            raise TaskExecutionError("Task disappeared during sandbox testing")

        # 3. 任务必须仍处于 testing。
        if task.status != "testing":
            raise TaskStateConflictError("Task is no longer running sandbox tests")

        # 4. 使用 task_id 和 test_run_id 查询对应记录。
        test_run = test_run_repo.get_test_run(
            session,
            task_id=context.task_id,
            test_run_id=context.test_run_id,
        )

        # 5. TestRun 不存在时抛 TaskExecutionError。
        if test_run is None:
            raise TaskExecutionError("Task disappeared during sandbox testing")

        # 6. TestRun 必须仍处于 running。
        if test_run.status != "running":
            raise TaskStateConflictError("Test run is no longer active")

        # 7. snapshot_hash 不应被重复写入。
        if test_run.snapshot_hash is not None:
            raise TaskStateConflictError("Test run snapshot is already recorded")

        # 8. 调用 Repository 保存 snapshot_hash。
        test_run_repo.set_test_run_snapshot_hash(
            session,
            test_run=test_run,
            snapshot_hash=snapshot_hash,
        )
