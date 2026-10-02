from uuid import UUID
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.exc import DBAPIError

from ..db.session import SessionLocal

from ..core.exceptions import (
    RepositoryBusyError,
    TaskExecutionError,
    InvalidTaskInputError,
    SandboxPreparationError,
)
from ..db.repositories import (
    repository_repo,
    task_repo,
    test_run_repo,
)
from ..schemas.testing import (
    TestRunValidityRead,
    TestRunRead,
)
from .sandbox_snapshot_service import prepare_python_test_snapshot


# 查询某个任务下的一次测试执行。
# None 表示任务或对应 TestRun 不存在。
def get_task_test_run(
    task_id: UUID,
    test_run_id: UUID,
) -> TestRunRead | None:
    with SessionLocal() as session:
        # 1. 查询任务。
        #    如果任务不存在，返回 None。
        task = task_repo.get_task(
            session,
            task_id=task_id,
        )

        if task is None:
            return None

        # 2. 调用 test_run_repo.get_test_run。
        test_run = test_run_repo.get_test_run(
            session,
            task_id=task_id,
            test_run_id=test_run_id,
        )

        if test_run is None:
            return None

        # 3. 必须在 Session 关闭前转换成 TestRunRead。
        return TestRunRead.model_validate(test_run)


# 分页查询一个任务的全部测试执行记录。
# None 表示任务不存在；空列表表示任务存在但还没有执行过测试。
def list_task_test_runs(
    task_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[TestRunRead] | None:
    # 1. 防御性校验。
    #    FastAPI 路由以后也会校验，但 Service 不能依赖 HTTP 层。
    if not 1 <= limit <= 100:
        raise InvalidTaskInputError("limit must be between 1 and 100")

    if offset < 0:
        raise InvalidTaskInputError("offset must be nonnegative")

    with SessionLocal() as session:
        # 2. 查询任务。
        #    任务不存在时返回 None。
        task = task_repo.get_task(session, task_id=task_id)

        if task is None:
            return None

        # 3. 调用 test_run_repo.list_test_runs。
        #    Repository 已经负责 started_at、id 倒序和分页。
        test_runs = test_run_repo.list_test_runs(
            session,
            task_id=task_id,
            limit=limit,
            offset=offset,
        )

        # 4. 在数据库会话内将所有 ORM 对象转换为 TestRunRead。
        result: list[TestRunRead] = []

        for test_run in test_runs:
            result.append(TestRunRead.model_validate(test_run))

        return result


# 实现有效性判断
def get_task_test_run_validity(
    task_id: UUID,
    test_run_id: UUID,
) -> TestRunValidityRead | None:
    try:
        with TemporaryDirectory(
            prefix="repopilot-validity-"
        ) as temporary_directory:
            with SessionLocal.begin() as session:
                # 1. 查询任务；不存在返回 None。
                task = task_repo.get_task(session, task_id=task_id)

                if task is None:
                    return None

                # 2. 使用 task_id 和 test_run_id 查询 TestRun。
                test_run = test_run_repo.get_test_run(
                    session,
                    task_id=task_id,
                    test_run_id=test_run_id,
                )

                if test_run is None:
                    return None

                recorded_hash = test_run.snapshot_hash

                # 3. 旧记录或快照准备失败的记录没有 hash，
                #    不扫描当前工作区，直接返回“无法判断”。
                if recorded_hash is None:
                    return TestRunValidityRead(
                        task_id=task_id,
                        test_run_id=test_run_id,
                        recorded_snapshot_hash=None,
                        current_snapshot_hash=None,
                        is_current=None,
                    )

                # 4. 锁定关联 Repository。
                #    SQLSTATE 55P03 表示 NOWAIT 行锁冲突。
                try:
                    repository = repository_repo.get_repository_for_update(
                        session,
                        repository_id=task.repository_id,
                    )
                except DBAPIError as exc:
                    if getattr(exc.orig, "sqlstate", None) == "55P03":
                        raise RepositoryBusyError("Repository is busy") from exc
                    raise

                # 5. 仓库不存在或没有 workspace_path 时，
                #    无法重新计算当前源码 hash。
                if repository is None or not repository.workspace_path:
                    raise TaskExecutionError("Task workspace is unavailable")

                # 6. 使用与真实测试完全相同的快照函数，
                #    防止比较算法与测试算法逐渐产生差异。
                current_snapshot = prepare_python_test_snapshot(
                    Path(repository.workspace_path),
                    Path(temporary_directory),
                )

                current_hash = current_snapshot.snapshot_hash

                return TestRunValidityRead(
                    task_id=task_id,
                    test_run_id=test_run_id,
                    recorded_snapshot_hash=recorded_hash,
                    current_snapshot_hash=current_hash,
                    is_current=(recorded_hash == current_hash),
                )
    except OSError as exc:
        raise SandboxPreparationError("Cannot prepare validity snapshot") from exc
