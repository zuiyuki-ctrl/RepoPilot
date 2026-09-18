from uuid import UUID

from ..schemas.repository_file import RepositoryFileRead
from ..core.config import WORKSPACE_ROOT
from .workspace_service import create_workspace
from ..core.exceptions import InvalidRepositoryInputError
from ..db.repositories import repository_repo, repository_file_repo
from ..db.session import SessionLocal
from ..schemas.repository import RepositoryCreate, RepositoryRead
from .repository_source import (
    validate_source_path,
    validate_git_root,
    read_git_metadata,
)

import logging
logger = logging.getLogger(__name__)

# 注册流程：检查输入/Git → 克隆指定提交到独立工作副本 → 保存仓库记录。
# 返回接口对象；此时还没有扫描或分块。数据库写入失败时保留副本并记录日志。
def create_repository(data: RepositoryCreate) -> RepositoryRead:
    name = data.name.strip()

    if not name:
        raise InvalidRepositoryInputError("Repository name must not be blank")

    if not data.source_path.strip():
        raise InvalidRepositoryInputError("Source path must not be blank")

    # 先检查源仓库并创建副本，成功后才开启数据库事务写入登记记录。
    source_path = validate_source_path(data.source_path)
    validate_git_root(source_path)
    metadata = read_git_metadata(source_path)

    workspace_path = create_workspace(workspace_root=WORKSPACE_ROOT, source_path=source_path, commit_hash=metadata.commit_hash)

    try:
        with SessionLocal.begin() as session:
            repository = repository_repo.create_repository(
                session,
                name=name,
                source_path=str(source_path),
                commit_hash=metadata.commit_hash,
                git_branch=metadata.git_branch,
                workspace_path=str(workspace_path),
            )

            result = RepositoryRead.model_validate(repository)
    except Exception as ex:
        logger.exception("Repository persistence failed; workspace retained at %s",workspace_path,)
        raise

    return result


# 查询登记信息并转换为接口对象；不存在返回 None，交给路由转换为 404。
def get_repository(repository_id: UUID) -> RepositoryRead | None:
    # 1. 使用 with SessionLocal() as session
    with SessionLocal() as session:
        # 2. 调用数据访问层的 get_repository
        repository = repository_repo.get_repository(session, repository_id)
        # 3. 查不到时返回 None
        if repository is None:
            return None
        # 4. 查到时，在 Session 关闭前转换为 RepositoryRead
        '''
        Repository：关联数据库映射和 Session 状态
            ↓
        RepositoryRead：保存要交给调用方的数据
        '''
        return RepositoryRead.model_validate(repository)

# 查询已入库的文件清单，不触发扫描；None=仓库不存在，[]=仓库存在但没有文件记录。
def list_repository_files(
    repository_id: UUID,
) -> list[RepositoryFileRead] | None:
    with SessionLocal() as session:
        # 1. 查询仓库是否存在。
        result = repository_repo.get_repository(session, repository_id)

        # 2. 仓库不存在，返回 None。
        if result is None:
            return None

        # 3. 调用 repository_file_repo.list_repository_files
        repository_files = repository_file_repo.list_repository_files(session, repository_id=repository_id)

        # 4. 逐个将 ORM 对象转换成 RepositoryFileRead
        repository_file_reads: list[RepositoryFileRead] = []
        for repository_file in repository_files:
            repository_file_reads.append(RepositoryFileRead.model_validate(repository_file))

        # 5. 在 Session 关闭前完成转换并返回列表。
        return repository_file_reads
