from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..core.exceptions import TaskStateConflictError, TaskExecutionError
from ..db.repositories import task_repo, task_event_repo, test_run_repo
from ..schemas.task import TaskRead
from ..db.models import AgentTask
from ..schemas.reflection import ReflectionFinishedEventPayload
from ..schemas.testing import TestRunRead, TestExecutionEventPayload
from ..schemas.workspace import TaskWorkspaceDiffRead
from ..db.session import SessionLocal
from ..schemas.task_report import TaskExecutionReport, TaskFailureSummary


# 从终止时的历史事件还原成功或失败报告，不使用当前工作区替代历史依据。
def get_task_execution_report(
    task_id: UUID,
) -> TaskExecutionReport | None:

    with SessionLocal.begin() as session:
        task = task_repo.get_task(session, task_id)

        if task is None:
            return None

        if task.task_type != "plan" or task.status not in ("completed", "failed"):
            raise TaskStateConflictError

        if task.status == "failed":
            return _build_failed_report(session, task=task)

        # ② 查询当前任务最近的 TASK_COMPLETED，命名为 completion_event。
        # - 已完成任务没有完成事件：抛 TaskExecutionError。
        # - 检查 completion_event.payload 是字典。
        completion_event = task_event_repo.get_latest_task_event_by_type(
            session,
            task_id=task.id,
            event_type="TASK_COMPLETED"
        )

        if completion_event is None:
            raise TaskExecutionError

        if not isinstance(completion_event.payload, dict):
            raise TaskExecutionError

        # ③ 从 完成事件的 payload 读取 test_run_id。
        # - 要求是字符串，再转换为 UUID。
        # - 字段缺失、类型不对、格式错误：抛 TaskExecutionError。
        # - 用当前任务 ID 和转换后的运行 ID调用 test_run_repo.get_test_run()。
        # - 查不到，或记录不满足 finished、未超时、退出码为 0：抛 TaskExecutionError。
        # 这里不能读取“最新测试”替代，因为报告应该展示完成时确认的那一次测试。
        test_run_id = completion_event.payload.get("test_run_id")

        if not isinstance(test_run_id, str):
            raise TaskExecutionError("Stored test run ID is invalid")
        try:
            test_run_id = UUID(test_run_id)
        except ValueError as exc:
            raise TaskExecutionError("Stored test run ID is invalid") from exc

        test_run = test_run_repo.get_test_run(session, task_id=task_id, test_run_id=test_run_id)
        if (
            test_run is None
            or test_run.status != "finished"
            or test_run.timed_out
            or test_run.exit_code != 0
        ):
            raise TaskExecutionError

        # ④ 读取 completion_event.payload.get("final_diff")。
        # - 为 None：报告中返回 final_diff=None。
        # - 否则用 TaskWorkspaceDiffRead.model_validate() 转换。
        # - 转换失败：转为 TaskExecutionError。
        # - 转换后确认 task_id 和 repository_id 与当前任务一致；不一致同样报内部数据异常。
        final_diff_data = completion_event.payload.get("final_diff")
        try:
            final_diff = (
                TaskWorkspaceDiffRead.model_validate(final_diff_data)
                if final_diff_data is not None else None
            )
            if final_diff is not None and (
                final_diff.task_id != task.id
                or final_diff.repository_id != task.repository_id
            ):
                raise TaskExecutionError("Stored completion diff belongs to another task or repository")

            result = TaskExecutionReport(
                task=TaskRead.model_validate(task),
                test_run=TestRunRead.model_validate(test_run),
                completion_event_sequence=completion_event.sequence,
                final_diff=final_diff,
            )
        except ValidationError as exc:
            raise TaskExecutionError("Stored task report data is invalid") from exc

    return result


# 使用同一会话读取最近的失败依据；反思停止时只关联它实际分析的测试，不生成当前差异。
def _build_failed_report(
    session: Session,
    *,
    task: AgentTask,
) -> TaskExecutionReport:
    if not isinstance(task.error, str) or not task.error.strip():
        raise TaskExecutionError("Failed task has no stored reason")

    events = [
        task_event_repo.get_latest_task_event_by_type(
            session, task_id=task.id, event_type=event_type,
        )
        for event_type in ("TASK_FAILED", "REFLECTION_FINISHED")
    ]
    events = [event for event in events if event is not None]
    if not events:
        raise TaskExecutionError("Failed task has no failure event")
    failure_event = max(events, key=lambda event: event.sequence)

    reflection = None
    test_run_read = None
    try:
        if failure_event.event_type == "REFLECTION_FINISHED":
            reflection_payload = ReflectionFinishedEventPayload.model_validate(failure_event.payload)
            if (
                reflection_payload.sequence != failure_event.sequence
                or reflection_payload.decision.should_retry is not False
                or reflection_payload.test_event_sequence >= failure_event.sequence
            ):
                raise TaskExecutionError("Stored reflection is not a valid failure basis")
            reflection = reflection_payload.decision

            test_run_read = _read_failed_test_run(
                session,
                task_id=task.id,
                test_event_sequence=reflection_payload.test_event_sequence,
                failure_event_sequence=failure_event.sequence,
            )
        elif failure_event.event_type == "TASK_FAILED":
            if not isinstance(failure_event.payload, dict):
                raise TaskExecutionError("Stored task failure payload is invalid")
            if failure_event.payload.get("reason_code") == "retry_budget_exhausted":
                test_run_read = _read_failed_test_run(
                    session,
                    task_id=task.id,
                    test_event_sequence=failure_event.payload.get("test_event_sequence"),
                    failure_event_sequence=failure_event.sequence,
                )
        else:
            raise TaskExecutionError("Unsupported failure event type")

        return TaskExecutionReport(
            task=TaskRead.model_validate(task),
            failure=TaskFailureSummary(
                reason=task.error,
                event_sequence=failure_event.sequence,
                event_type=failure_event.event_type,
                reflection=reflection,
            ),
            test_run=test_run_read,
            final_diff=None,
            completion_event_sequence=None,
        )
    except ValidationError as exc:
        raise TaskExecutionError("Stored failed task report data is invalid") from exc


# 仅还原终止事件引用的历史失败测试；沿用调用方会话，不检查当前快照或提交事务。
def _read_failed_test_run(
    session: Session,
    *,
    task_id: UUID,
    test_event_sequence: int,
    failure_event_sequence: int,
) -> TestRunRead | None:
    if (
        type(test_event_sequence) is not int
        or test_event_sequence < 1
        or test_event_sequence >= failure_event_sequence
    ):
        raise TaskExecutionError("Referenced test sequence is invalid")

    test_event = task_event_repo.get_task_event_by_sequence(
        session, task_id=task_id, sequence=test_event_sequence,
    )
    if (
        test_event is None
        or test_event.event_type != "TEST_EXECUTION_FINISHED"
        or test_event.sequence != test_event_sequence
    ):
        raise TaskExecutionError("Referenced test event is unavailable")

    try:
        test_payload = TestExecutionEventPayload.model_validate(test_event.payload)
        passed = not test_payload.timed_out and test_payload.exit_code == 0
        if (
            test_payload.sequence != test_event.sequence
            or passed != test_payload.passed
            or passed
        ):
            raise TaskExecutionError("Referenced test event is not a consistent failed result")

        if test_payload.test_run_id is None:
            return None
        try:
            test_run_id = UUID(test_payload.test_run_id)
        except ValueError as exc:
            raise TaskExecutionError("Stored test run ID is invalid") from exc
        test_run = test_run_repo.get_test_run(session, task_id=task_id, test_run_id=test_run_id)
        if (
            test_run is None
            or test_run.status != "finished"
            or test_run.exit_code != test_payload.exit_code
            or test_run.timed_out != test_payload.timed_out
        ):
            raise TaskExecutionError("Stored test run disagrees with its failure event")
        return TestRunRead.model_validate(test_run)
    except ValidationError as exc:
        raise TaskExecutionError("Stored failed test data is invalid") from exc
