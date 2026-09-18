from uuid import UUID

from sqlalchemy.orm import Session

from .repository_chunking_service import ChunkedFile
from ..db.repositories.repository_file_repo import save_repository_file
from ..db.repositories.code_chunk_repo import (
    create_code_chunk,
    delete_code_chunks_for_file,
    list_code_chunks
)
from ..db.repositories.repository_repo import get_repository
from ..schemas.code_chunk import CodeChunkRead
from ..db.session import SessionLocal


# 在调用方的事务内保存一个文件，并用本次块完全替换旧块，返回写入块数。
# 文件内容未变也会重建块，因此文件 ID 可保持不变，块 ID 不保证稳定。
# chunks 为空时仍保留文件记录并删去旧块；本函数只 flush，不自行 commit。
def save_chunked_file(
    session: Session,
    *,
    repository_id: UUID,
    chunked_file: ChunkedFile,
) -> int:
    metadata = chunked_file.metadata

    # 1. 调用 save_repository_file，保存文件元数据
    repository_file = save_repository_file(
        session,
        repository_id=repository_id,
        path=metadata.path,
        language=metadata.language,
        file_hash=metadata.file_hash,
        size=metadata.size,
    )

    # 2. 删除该文件已有的代码块。
    # 调用 delete_code_chunks_for_file。
    # file_id 使用 repository_file.id。
    delete_code_chunks_for_file(session, repository_id=repository_id, file_id=repository_file.id)

    # 3. 遍历 chunked_file.chunks。
    for chunk in chunked_file.chunks:
        # 调用 create_code_chunk：
        create_code_chunk(
            session,
            repository_id=repository_id,
            file_id=repository_file.id,
            file_path=repository_file.path,
            symbol_name=chunk.symbol_name,
            symbol_type=chunk.symbol_type,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            content=chunk.content,
        )

    # 4. 返回本次保存的代码块数量
    return len(chunked_file.chunks)

# 查询已入库的块，不重新扫描磁盘。
# None 表示仓库不存在；[] 表示仓库存在但当前筛选/分页没有结果。
# file_path 是精确匹配的仓库相对路径；会话关闭前转换为接口响应对象。
def list_repository_chunks(
    repository_id: UUID,
    *,
    file_path: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[CodeChunkRead] | None:
    with SessionLocal() as session:
        # 1. 使用 get_repository 查询仓库。
        # 不存在时返回 None。
        result = get_repository(session, repository_id)
        if result is None:
            return None

        # 2. 调用数据访问层的 list_code_chunks。
        # 传递 session 和全部筛选、分页参数。
        code_chunks = list_code_chunks(
            session,
            repository_id=repository_id,
            file_path=file_path,
            limit=limit,
            offset=offset
        )

        # 3. 在会话内部，将每个 ORM 对象转换为 CodeChunkRead。
        # 提示：CodeChunkRead.model_validate(chunk)
        # 返回转换后的列表。
        code_chunk_read_list : list[CodeChunkRead] = []
        for code_chunk in code_chunks:
            code_chunk_read_list.append(CodeChunkRead.model_validate(code_chunk))

        return code_chunk_read_list


