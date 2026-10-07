from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models import AgentTask


# 插入 created 状态的任务并 flush，取得默认字段；任务服务负责提交事务和后续执行。
def create_task(
    session: Session,
    *,
    repository_id: UUID,
    user_request: str,
    task_type: str,
    run_config: dict | None = None,
) -> AgentTask:

    task = AgentTask(
        repository_id=repository_id,
        user_request=user_request,
        task_type=task_type,
        status="created",
        run_config=run_config,
    )

    session.add(task)

    session.flush()

    return task


# 按主键查询任务 ORM 对象，供服务层读取状态和结果；不存在返回 None。
def get_task(
    session: Session,
    task_id: UUID,
) -> AgentTask | None:
    return session.get(AgentTask, task_id)

# 按任务 ID 查询并锁定对应行，协调执行、审核及事件编号分配；锁由调用方事务释放。
def get_task_for_update(
    session: Session,
    task_id: UUID,
) -> AgentTask | None:
    # 1. select(AgentTask)，按 id 筛选。
    statement = select(AgentTask).where(AgentTask.id == task_id)

    # 2. 添加 with_for_update()。
    statement = statement.with_for_update()

    # 3. 返回 scalar_one_or_none()。
    return session.execute(statement).scalar_one_or_none()


# 将已领取的任务标记为 running 并记录开始时间；供任务执行服务调用，只 flush 不提交。
def mark_task_running(
    session: Session,
    task: AgentTask,
) -> None:
    # 1. status 设置为 running。
    task.status = "running"

    # 2. started_at 设置为当前 UTC 时间。
    task.started_at = datetime.now(timezone.utc)

    # 3. session.flush，不 commit。
    session.flush()


# 保存任务执行结果并标记 completed、清除错误、记录完成时间；提交由任务服务负责。
def mark_task_completed(
    session: Session,
    task: AgentTask,
    *,
    result: dict,
) -> None:
    # 1. status 设置为 completed。
    task.status = "completed"

    # 2. 保存 result，error 设为 None。
    task.result = result
    task.error = None

    # 3. 填写 completed_at，flush。
    task.completed_at = datetime.now(timezone.utc)
    session.flush()


# 将任务标记为 failed，清空结果并保存受控错误说明和结束时间；供执行失败收尾使用。
def mark_task_failed(
    session: Session,
    task: AgentTask,
    *,
    error: str,
) -> None:
    # 1. status 设置为 failed。
    task.status = "failed"

    # 2. 保存受控错误说明，result 设为 None。
    task.result = None
    task.error = error

    # 3. 填写 completed_at，flush。
    task.completed_at = datetime.now(timezone.utc)
    session.flush()


# 是否允许审核，由服务层判断；数据访问层只负责落实已确定的变更
def save_plan_review(
    session: Session,
    task: AgentTask,
    *,
    decision: str,
    comment: str | None,
) -> None:
    # 1. 取得当前 UTC 时间，整个函数复用同一个时间值。
    reviewed_at = datetime.now(timezone.utc)

    # 2. 保存 decision、comment 和 reviewed_at。
    task.review_decision = decision
    task.review_comment = comment
    task.reviewed_at = reviewed_at

    # 3. 根据 decision 更新状态：
    if decision == "approved":
        task.status = "approved"
        task.completed_at = None

    if decision == "rejected":
        task.status = "rejected"
        task.completed_at = reviewed_at

    # 4. flush，不 commit。
    session.flush()

# 保存已生成的计划并将任务置为 awaiting_review，供人工审核接续执行；只 flush，由服务提交。
def mark_task_awaiting_review(
    session: Session,
    task: AgentTask,
    *,
    result: dict,
) -> None:
    # 1. 将 status 设置成 awaiting_review。
    task.status = "awaiting_review"

    # 2. 保存结构化计划 result。
    task.result = result

    # 3. 将 error 设置为 None。
    task.error = None

    # 4. completed_at 保持 None，因为整个任务尚未结束。
    task.completed_at = None

    # 5. flush，不 commit。
    session.flush()


# 将任务设为 executing，清除错误及完成时间并 flush；用于开始执行或测试后恢复执行。
# 不自行提交事务，状态前置条件由调用服务检查。
def mark_task_executing(
    session: Session,
    task: AgentTask,
) -> None:
    # 1. status 设置为 executing。
    task.status = "executing"

    # 2. 清除旧错误；completed_at 保持 None。
    task.error = None
    task.completed_at = None

    # 3. flush，不 commit。
    session.flush()


# 将任务设为 testing，清除错误及完成时间并 flush；由测试服务在领取测试权时调用。
# 不自行检查批准状态或提交事务，交给调用服务统一处理。
def mark_task_testing(
    session: Session,
    task: AgentTask,
) -> None:
    """
    将正在执行修改的任务切换到沙箱测试状态。
    只 flush，事务提交由服务层负责。
    """
    # 把状态改成 testing。
    task.status = "testing"

    # 清除旧错误，保持 completed_at 为 None。
    task.error = None
    task.completed_at = None

    session.flush()


# 将任务设为 reflecting 并增加一次重试计数，清除错误及完成时间后 flush。
# 调用方必须先锁定任务并检查重试预算，与反思开始事件一起提交。
def mark_task_reflecting(
    session: Session,
    task: AgentTask,
) -> None:
    """
    消耗一次重试额度并把任务切换为 reflecting。
    调用方必须已经锁定任务并验证剩余额度。
    """

    task.retry_count += 1

    # 状态改成 reflecting，清除旧错误，
    # completed_at 保持 None。
    task.status = "reflecting"
    task.error = None
    task.completed_at = None

    session.flush()


def mark_plan_task_failed(
    session: Session,
    task: AgentTask,
    *,
    error: str,
) -> None:
    task.status = "failed"

    task.completed_at = datetime.now(timezone.utc)
    task.error = error

    session.flush()
