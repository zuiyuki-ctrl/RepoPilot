# 数据访问层：只操作仓库表。传入的 session 由 service 管理，flush 不等于提交事务。
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.repository import Repository

# 将一条新仓库记录写入当前事务
# 插入仓库登记记录并取得默认 ID；不负责检查 Git 或创建磁盘工作副本。
def create_repository(
    session: Session,
    *,
    name: str,
    source_path: str,
    commit_hash: str,
    git_branch: str | None,
    workspace_path: str,
) -> Repository:
    # 1. 创建 Repository 对象
    repository = Repository(
        name=name,
        source_path=source_path,
        commit_hash=commit_hash,
        git_branch=git_branch,
        workspace_path=workspace_path,
    )

    # 2. 加入 session
    session.add(repository)

    # 3. flush，让默认 ID 等值生成
    session.flush()

    # 4. 返回对象
    return repository

# 按唯一 ID 查找仓库
# 按数据库主键查询，不存在返回 None；不会访问磁盘或 Git。
# 按主键查询，找不到返回 None
# 指定查询的目标 ORM 模型类为 Repository
def get_repository(
    session: Session,
    repository_id: UUID,
) -> Repository | None:
    return session.get(Repository, repository_id)


# 获取事务内的排他行锁，防止同一仓库同时 scan/index；不存在返回 None。
# NOWAIT 表示锁被占用就立刻报错，由 service 将 SQLSTATE 55P03 转为忙碌异常。
# 锁随事务提交/回滚释放；它不阻止外部编辑器修改磁盘文件。
def get_repository_for_update(
    session: Session,
    repository_id: UUID,
) -> Repository | None:
    # 1. 构造 select(Repository)
    statement = select(Repository)

    # 2. 按 Repository.id == repository_id 筛选
    statement = statement.where(Repository.id == repository_id)

    # 3. 添加行锁，锁被占用时立即报错，不等待
    statement = statement.with_for_update(nowait=True)

    # 4. 执行查询，返回唯一仓库对象或 None
    return session.execute(statement).scalar_one_or_none()
