from pathlib import Path
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..db.repositories import task_event_repo, test_run_repo, task_repo, repository_repo
from ..schemas.workspace import TaskWorkspaceDiffRead
from .workspace_git_service import read_workspace_diff
from ..schemas.task import TaskPlanResult
from .test_run_service import check_test_run_snapshot
from ..db.session import SessionLocal
from ..schemas.task import TaskRead
from ..schemas.testing import TestExecutionEventPayload
from ..core.exceptions import TaskStateConflictError, TaskExecutionError
from ..db.models import TestRun


# 读取完成时的工作副本差异，并转换成现有的 Diff 响应模型
def _capture_completion_diff(
        session: Session,
        *,
        task_id: UUID,
        repository_id: UUID,
) -> TaskWorkspaceDiffRead:

    repository = repository_repo.get_repository(session, repository_id=repository_id)

    if repository is None or not repository.workspace_path:
        raise TaskExecutionError

    diff_result = read_workspace_diff(Path(repository.workspace_path))
    return TaskWorkspaceDiffRead(
        task_id=task_id,
        repository_id=repository_id,
        diff=diff_result.diff,
        changed_files=diff_result.changed_files,
        untracked_files=diff_result.untracked_files,
        truncated=diff_result.truncated,
    )

# task_id：要完成的任务。
# test_run_id：用户在请求体中指定的测试运行 ID
def _require_latest_passed_test(
        session: Session,
        *,
        task_id: UUID,
        test_run_id: UUID,
) -> tuple[TestRun, int]:
    test_event = task_event_repo.get_latest_task_event_by_type(
        session,
        task_id=task_id,
        event_type="TEST_EXECUTION_FINISHED",
    )

    if test_event is None:
        raise TaskStateConflictError

    try:
        test_payload = TestExecutionEventPayload.model_validate(test_event.payload)
    except ValidationError:
        raise TaskExecutionError

    if test_payload.sequence != test_event.sequence:
        raise TaskExecutionError

    # ③ 检查 test_payload.test_run_id：
    # - 为 None：历史结果缺少关联，抛 TaskStateConflictError，要求重新测试。
    # - 转为 UUID 失败：抛 TaskExecutionError。
    # - 转换后的 UUID 与用户提交的 test_run_id 不同：抛 TaskStateConflictError，表示用户确认的不是最近一次完整测试。
    if test_payload.test_run_id is None:
        raise TaskStateConflictError

    try:
        _test_run_id = UUID(test_payload.test_run_id)
    except ValueError:
        raise TaskExecutionError

    if test_run_id != _test_run_id:
        raise TaskStateConflictError

    # ④ 分别查询当前任务最近的以下事件：
    # (
    #     "TEST_EXECUTION_STARTED",
    #     "TEST_EXECUTION_FAILED",
    #     "FILE_MODIFIED",
    # )
    # 只要查出的事件不为空，且其 sequence > test_event.sequence，就拒绝完成
    for event in (
            "TEST_EXECUTION_STARTED",
            "TEST_EXECUTION_FAILED",
            "FILE_MODIFIED",
    ):
        result = task_event_repo.get_latest_task_event_by_type(
            session,
            task_id=task_id,
            event_type=event,
        )
        if result is not None and result.sequence > test_event.sequence:
            raise TaskStateConflictError

    # 此时最近的“完整测试”仍然是 R1，但不能忽略后面的失败尝试。
    # ⑤ 调用 test_run_repo.get_test_run()，同时传入当前 task_id 和请求中的 test_run_id
    test_run = test_run_repo.get_test_run(
        session,
        task_id=task_id,
        test_run_id=test_run_id
    )
    if test_run is None:
        raise TaskExecutionError

    if (
            test_run.status != "finished"
            or test_run.exit_code != test_payload.exit_code
            or test_run.timed_out != test_payload.timed_out
    ):
        raise TaskExecutionError

    # ⑥ 从 TestRun 对象计算：
    passed = not test_run.timed_out and test_run.exit_code == 0

    # - 与 测试结束事件中的 test_payload.passed 不一致：抛 TaskExecutionError。
    # - 结果一致但 passed=False：抛 TaskStateConflictError，失败测试不能作为完成依据。
    if passed != test_payload.passed:
        raise TaskExecutionError

    if not passed:
        raise TaskStateConflictError

    # 返回
    # 这部分与 Reflection 的检查有相似之处，但一个要求通过，一个要求失败
    return test_run, test_payload.sequence


def complete_plan_task(
        task_id: UUID,
        *,
        test_run_id: UUID,
) -> TaskRead | None:
    # 1. 开启 SessionLocal.begin()。
    with SessionLocal.begin() as session:
        # 2. 用 task_repo.get_task_for_update 锁定任务。
        #    不存在返回 None。
        task = task_repo.get_task_for_update(
            session,
            task_id=task_id,
        )

        if task is None:
            return None

        # 3. 要求：
        #    task_type == "plan"
        #    status == "executing"
        #    review_decision == "approved"
        if not (
                task.task_type == "plan"
                and task.status == "executing"
                and task.review_decision == "approved"
        ):
            raise TaskStateConflictError

        # 4. 用 TaskPlanResult.model_validate(task.result) 验证保存的计划。
        #    校验失败或计划中的 repository_id 与任务不一致：
        #    抛 TaskExecutionError。
        try:
            task_result = TaskPlanResult.model_validate(task.result)

        except ValidationError as exc:
            raise TaskExecutionError("Stored plan is invalid") from exc

        if task_result.repository_id != task.repository_id:
            raise TaskExecutionError

        # 5. 调用 _require_latest_passed_test，
        #    得到 test_run 和 test_event_sequence。
        test_run, test_event_sequence = _require_latest_passed_test(
            session,
            task_id=task_id,
            test_run_id=test_run_id
        )

        # 6. 使用同一个 session 调用 check_test_run_snapshot。
        #    repository_id 传 task.repository_id；
        #    test_run 传第 5 步返回的记录。
        #    is_current 不是 True 时抛 TaskStateConflictError。
        validity = check_test_run_snapshot(
            session,
            repository_id=task.repository_id,
            test_run=test_run,
        )

        if not validity.is_current:
            raise TaskStateConflictError("A current test snapshot is required before completion")


        completion_diff = _capture_completion_diff(
            session,
            task_id=task.id,
            repository_id=task.repository_id,
        )


        # 7. 调用已有 mark_task_completed。
        #    result 传第 4 步验证后的计划 model_dump(mode="json")。
        task_repo.mark_task_completed(session, task, result=task_result.model_dump(mode="json"))

        # 8. 使用同一个 session 追加 TASK_COMPLETED 事件。
        task_event_repo.append_task_event(
            session,
            task_id=task_id,
            event_type="TASK_COMPLETED",
            node_name="task_completion_service",
            message="Task completed successfully",
            payload={
                "step_id": "complete",
                "attempt": 1,
                "test_run_id": str(test_run.id),
                "test_event_sequence": test_event_sequence,
                "snapshot_hash": test_run.snapshot_hash,
                "completed_at": task.completed_at.isoformat(),
                "completion_mode": "manual",
                "final_diff": completion_diff.model_dump(mode="json"),
            }
        )

        # 9. 会话内转换为 TaskRead。
        result = TaskRead.model_validate(task)


    # 退出事务成功后返回。
    return result
