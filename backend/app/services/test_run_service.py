from uuid import UUID
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ..db.models import TestRun
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

        return check_test_run_snapshot(session, repository_id=task.repository_id, test_run=test_run)


# 在现有事务中检查快照
# 回答源码是否一致
def check_test_run_snapshot(
    session: Session,
    *,
    repository_id: UUID,
    test_run: TestRun,
) -> TestRunValidityRead:
    # 1. 读取 test_run.snapshot_hash。
    #    为 None 时直接返回 is_current=None，两个 hash 均为 None。
    snapshot_hash = test_run.snapshot_hash
    if snapshot_hash is None:
        return TestRunValidityRead(
            task_id=test_run.task_id,
            test_run_id=test_run.id,
            recorded_snapshot_hash=None,
            current_snapshot_hash=None,
            is_current=None,
        )

    # 2. 使用传入的 session 调用 get_repository_for_update。
    #    SQLSTATE 55P03 转成 RepositoryBusyError；其他数据库异常原样抛出。
    try:
        repository = repository_repo.get_repository_for_update(session, repository_id)

    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == "55P03":
            raise RepositoryBusyError("Repository is busy") from exc
        raise

    # 3. 仓库不存在或 workspace_path 为空，抛 TaskExecutionError。
    if repository is None or not repository.workspace_path:
        raise TaskExecutionError("Task workspace is unavailable")

    # 4. 创建 TemporaryDirectory。
    #    调用 prepare_python_test_snapshot，获取 current_hash。
    try:
        with TemporaryDirectory() as temporary_directory:
            snapshot = prepare_python_test_snapshot(Path(repository.workspace_path), Path(temporary_directory))

            current_hash = snapshot.snapshot_hash

            # 5. 返回 TestRunValidityRead：
            return TestRunValidityRead(
                task_id=test_run.task_id,
                test_run_id=test_run.id,
                recorded_snapshot_hash=test_run.snapshot_hash,
                current_snapshot_hash=current_hash,
                is_current=(snapshot_hash == current_hash),
            )

    # 6. 临时目录创建、清理等 OSError 转成 SandboxPreparationError。
    except OSError as exc:
        raise SandboxPreparationError("Cannot prepare validity snapshot") from exc