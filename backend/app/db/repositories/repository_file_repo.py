# 文件表的数据访问层；只修改记录，不创建/删除磁盘文件，事务由调用方提交。
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from ..models.repository_file import RepositoryFile


# 新增文件元数据并 flush，取得 ID 供代码块外键引用；重复路径由唯一约束拒绝。
def create_repository_file(
    session: Session,
    *,
    repository_id: UUID,
    path: str,
    language: str,
    file_hash: str,
    size: int,
) -> RepositoryFile:
    # 1. 创建 RepositoryFile 对象。
    # 将上面的六个业务参数分别赋给同名字段。
    # id、created_at、updated_at 交给现有默认值。
    repository_file = RepositoryFile(
        repository_id=repository_id,
        path=path,
        language=language,
        file_hash=file_hash,
        size=size,
    )

    # 2. 将对象加入传入的 session。
    session.add(repository_file)

    # 3. 执行 flush
    # 这里会执行 INSERT，并检查外键、唯一约束等。
    session.flush()

    # 4. 返回 RepositoryFile 对象
    return repository_file

# 按仓库 ID 和路径查找记录
# 用“仓库 + 相对路径”定位文件；同名文件在不同仓库中是不同记录。
def get_repository_file_by_path(
    session: Session,
    *,
    repository_id: UUID,
    path: str,
) -> RepositoryFile | None:
    # 1. 构造查询，查询对象是 RepositoryFile。
    # 提示：select(RepositoryFile)
    statement = select(RepositoryFile)

    # 2. 添加两个条件，必须同时满足：
    # RepositoryFile.repository_id == repository_id
    # RepositoryFile.path == path
    statement = statement.where(RepositoryFile.repository_id == repository_id, RepositoryFile.path == path)

    # 3. 执行查询，并返回唯一对象或 None
    return session.execute(statement).scalar_one_or_none()

# 不存在则新增，存在且变化则更新
# 有则按需更新、无则新增；更新保持文件 ID 和创建时间，供已有外键继续关联。
# 这里只同步元数据，不处理块；同仓库的并发写入由上层仓库行锁协调。
def save_repository_file(
    session: Session,
    *,
    repository_id: UUID,
    path: str,
    language: str,
    file_hash: str,
    size: int,
) -> RepositoryFile:
    # 1. 调用 get_repository_file_by_path，取得已有记录
    result = get_repository_file_by_path(session=session, repository_id=repository_id, path=path)

    # 2. 如果不存在：
    # 调用已有的 create_repository_file，传入全部参数，
    # 返回创建结果。
    if result is None:
        return create_repository_file(
            session=session,
            repository_id=repository_id,
            path=path,
            language=language,
            file_hash=file_hash,
            size=size,
        )

    # 3. 如果存在：
    # 比较 language、file_hash、size。
    # 全部相同，直接返回已有对象，不修改。
    if result.language == language and result.file_hash == file_hash and result.size == size:
        return result

    # 4. 有变化时：
    # 更新已有对象的 language、file_hash、size。
    # 不改变 id、repository_id、path、created_at
    result.language = language
    result.file_hash = file_hash
    result.size = size

    # 5. flush 后返回对象，不 commit。
    session.flush()
    return result

# 删除本次不再保留的旧记录
# 删除当前仓库中不在保留集合的文件记录；空集合表示清空该仓库文件记录。
# 调用前必须先清理关联块，避免外键约束失败；不影响其他仓库和磁盘内容。
def delete_stale_repository_files(
    session: Session,
    *,
    repository_id: UUID,
    retained_paths: set[str],
) -> None:
    # 1. 构造删除 RepositoryFile 的语句。
    statement = delete(RepositoryFile)

    # 2. 必须先限定 repository_id
    statement = statement.where(RepositoryFile.repository_id == repository_id)

    # 3. retained_paths 非空时：
    # 增加“path 不在 retained_paths 中”的条件
    if retained_paths:
        statement = statement.where(RepositoryFile.path.not_in(retained_paths))

    # 4. 执行删除语句。
    session.execute(statement)

# 查询指定仓库的文件
# 按相对路径升序返回已入库文件，未查到返回 []；不负责区分仓库是否存在。
def list_repository_files(
    session: Session,
    *,
    repository_id: UUID,
) -> list[RepositoryFile]:
    # 1. 构造 select(RepositoryFile)
    statement = select(RepositoryFile)

    # 2. 按 repository_id 筛选
    statement = statement.where(RepositoryFile.repository_id == repository_id)

    # 3. 按文件路径升序排列
    statement = statement.order_by(RepositoryFile.path)

    # 4. 执行查询，取出全部 ORM 对象并返回列表。
    return list(session.scalars(statement).all())
