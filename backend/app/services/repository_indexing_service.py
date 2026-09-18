from pathlib import Path
from uuid import UUID
from dataclasses import dataclass

from ..db.repositories.repository_file_repo import delete_stale_repository_files
from ..db.repositories.repository_repo import get_repository_for_update
from ..core.exceptions import RepositoryScanError, RepositoryBusyError
from ..db.repositories import repository_file_repo
from ..db.session import SessionLocal
from .repository_scanner import ScanResult, scan_repository
from ..db.repositories.code_chunk_repo import delete_stale_code_chunks
from .repository_chunking_service import chunk_repository
from .code_chunk_service import save_chunked_file
from .repository_scanner import SkippedFile

from sqlalchemy.exc import DBAPIError

# 将物理工作区中最新的 .py 文件扫描结果更新到数据库，同时清理已经物理删除的历史遗留文件记录。
# /scan 的事务入口：同步文件清单；仓库不存在返回 None。
# 不重建保留文件的块；修改源码后要调用 /index 才能更新块内容。
# 删除失效文件前先删其块，避免违反外键约束；异常时本次数据库修改全部回滚。
def sync_repository_files(
    repository_id: UUID,
) -> ScanResult | None:
    with SessionLocal.begin() as session:
        try:
            # 1. 使用 get_repository_for_update 查询并取得行锁
            repository = get_repository_for_update(session, repository_id)

        except DBAPIError as exc:
            # 2. 读取原始数据库异常的 SQLSTATE
            result = getattr(exc.orig, "sqlstate", None)

            # 3. 如果是 "55P03"，转换为 RepositoryBusyError
            # 55P03 表示 lock_not_available
            if result == "55P03":
                raise RepositoryBusyError("Repository is busy") from exc

            # 4. 其他数据库错误，使用裸 raise 继续抛出
            raise

        # 5. 仓库不存在，返回 None
        if repository is None:
            return None

        # 6. workspace_path 为空，抛 RepositoryScanError
        if repository.workspace_path is None:
            raise RepositoryScanError("Repository has no workspace")

        # 7. 调用 scan_repository，保存 scan_result
        # 注意：现在扫描也在同一个事务内
        scan_result = scan_repository(Path(repository.workspace_path))

        # 8. 沿用已有循环：
        # 保存每条文件记录，并填充 retained_paths
        retained_paths: set[str] = set()
        for file in scan_result.files:
            repository_file_repo.save_repository_file(
                session,
                repository_id=repository_id,
                path=file.path,
                language=file.language,
                file_hash=file.file_hash,
                size=file.size,
            )
            retained_paths.add(file.path)

        # 9. 循环结束后清理旧记录
        # 9.1. 先清理不再保留的文件对应的代码块
        delete_stale_code_chunks(session, repository_id=repository_id, retained_paths=retained_paths)

        # 9.2. 再执行原有的文件记录清理
        delete_stale_repository_files(
            session,
            repository_id=repository_id,
            retained_paths=retained_paths,
        )

    # 10. 事务提交成功后返回 scan_result
    return scan_result

# 返回数量和跳过原因，避免接口为了显示“保存了多少块”，还得接收整个仓库的源码内容
@dataclass
class RepositoryChunkIndexResult:
    # /index 的结果摘要，不含完整源码；数量是本次有效总数，不是相对上次的新增数。
    repository_id: UUID
    file_count: int
    chunk_count: int
    skipped_files: list[SkippedFile]

# /index 的事务入口：锁仓库 → 分块 → 保存文件和块 → 清理失效记录 → 提交。
# 只读 workspace_path 的磁盘内容，不拉取源仓库，也不生成向量或更新 indexed_at。
# 仓库不存在返回 None；锁冲突抛 RepositoryBusyError；失败时整次写入回滚。
def index_repository_chunks(
    repository_id: UUID,
) -> RepositoryChunkIndexResult | None:
    with SessionLocal.begin() as session:
        # 1. 沿用 sync_repository_files 的查询及加锁逻辑：
        # - get_repository_for_update
        # - SQLSTATE 55P03 转换成 RepositoryBusyError
        # - 其他数据库异常继续抛出
        try:
            repository = get_repository_for_update(session, repository_id)
        except DBAPIError as exc:
            result = getattr(exc.orig, "sqlstate", None)

            if result == "55P03":
                raise RepositoryBusyError("Repository is busy") from exc
            raise

        # 2. 仓库不存在，返回 None。
        # workspace_path 为 None，抛 RepositoryScanError。
        if repository is None:
            return None
        if repository.workspace_path is None:
            raise RepositoryScanError("Repository has no workspace")

        # 3. 调用 chunk_repository。
        # 传入 Path(repository.workspace_path)。
        # 将结果保存为 chunking_result。
        chunking_result = chunk_repository(Path(repository.workspace_path))

        # 只有成功解析的文件才保留；原来有效、本次被跳过的文件也会清理旧记录。
        retained_paths: set[str] = set()
        chunk_count = 0

        # 4. 遍历 chunking_result.files。
        for chunked_file in chunking_result.files:
            # 调用 save_chunked_file，使用当前 session 和 repository_id。
            # 把返回的数量累加到 chunk_count。
            chunk_count += save_chunked_file(
                session,
                repository_id=repository_id,
                chunked_file=chunked_file,
            )

            # 将 chunked_file.metadata.path 加入 retained_paths。
            retained_paths.add(chunked_file.metadata.path)

        # 5. 清理未保留路径的旧代码块。
        delete_stale_code_chunks(
            session,
            repository_id=repository_id,
            retained_paths=retained_paths
        )

        # 6. 再清理未保留路径的旧文件记录。
        delete_stale_repository_files(
            session,
            repository_id=repository_id,
            retained_paths=retained_paths,
        )

        # 7. 创建 RepositoryChunkIndexResult，保存到 result
        result = RepositoryChunkIndexResult(
            repository_id=repository_id,
            file_count=len(chunking_result.files),
            chunk_count=chunk_count,
            skipped_files=chunking_result.skipped_files,
        )

    # 8. 退出事务、提交成功后，再返回 result。
    return result
