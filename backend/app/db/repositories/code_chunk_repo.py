# 块表的数据访问层：保存源码片段和来源位置，不负责 AST 解析；不自行提交事务。
from uuid import UUID
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import delete, select, or_

from ..models.code_chunk import CodeChunk

# 插入一条已经解析好的代码块并 flush；仓库、文件和路径的一致性由调用方保证。
def create_code_chunk(
    session: Session,
    *,
    repository_id: UUID,
    file_id: UUID,
    file_path: str,
    symbol_name: str,
    symbol_type: str,
    start_line: int,
    end_line: int,
    content: str,
    chunk_metadata: dict[str, Any] | None = None,
) -> CodeChunk:
    # 1. 创建 CodeChunk 对象。
    # 将参数分别赋给同名的模型属性。
    # chunk_metadata 为 None 时使用空字典，否则使用传入的值。
    code_chunk = CodeChunk(
        repository_id=repository_id,
        file_id=file_id,
        file_path=file_path,
        symbol_name=symbol_name,
        symbol_type=symbol_type,
        start_line=start_line,
        end_line=end_line,
        content=content,
        chunk_metadata=dict() if chunk_metadata is None else chunk_metadata,
    )

    # 2. 调用 session.add(...)，将对象加入当前会话。
    session.add(code_chunk)

    # 3. 调用 session.flush()，将插入操作发送到数据库。
    session.flush()

    # 4. 返回新建的 CodeChunk 对象。
    return code_chunk

# 重建单个文件的索引前删除其全部旧块，同时限定仓库和文件以收紧删除范围。
def delete_code_chunks_for_file(
    session: Session,
    *,
    repository_id: UUID,
    file_id: UUID,
) -> None:
    # 1. 构造针对 CodeChunk 的 delete 语句。
    statement = delete(CodeChunk)

    # 2. 添加两个筛选条件，必须同时满足：
    # CodeChunk.repository_id == repository_id
    # CodeChunk.file_id == file_id
    statement = statement.where(CodeChunk.repository_id == repository_id, CodeChunk.file_id == file_id)

    # 3. 使用 session.execute(stmt) 执行
    session.execute(statement)

# 先删除旧代码块 → 再删除旧文件记录
# 删除当前仓库中来源路径已失效的块；空保留集合表示删除该仓库的全部块。
# 必须先于文件记录清理执行；只删除数据库记录，不改动源码文件。
def delete_stale_code_chunks(
    session: Session,
    *,
    repository_id: UUID,
    retained_paths: set[str],
) -> None:
    # 1. 构造针对 CodeChunk 的 delete 语句。
    statement = delete(CodeChunk)

    # 2. 必须先限定 repository_id。
    # 无论 retained_paths 是否为空，都只能操作当前仓库。
    statement = statement.where(CodeChunk.repository_id == repository_id)

    # 3. retained_paths 非空时：
    # 增加“file_path 不在保留路径集合中”的条件
    if retained_paths:
        statement = statement.where(CodeChunk.file_path.not_in(retained_paths))

    # 4. 使用 session.execute(...) 执行，不提交事务。
    session.execute(statement)

# 分页读取已入库块；file_path 非 None 时按相对路径精确匹配，不做模糊搜索。
# 按路径、开始行、ID 排序使同一数据集分页稳定；索引重建后不保证分页快照不变。
# 参数越界抛 ValueError，查不到返回 []；仓库是否存在由上层服务判断。
def list_code_chunks(
    session: Session,
    *,
    repository_id: UUID,
    file_path: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[CodeChunk]:
    # 1. 校验分页参数。
    # 要求：1 <= limit <= 100，offset >= 0。
    # 不合法时抛出 ValueError。
    if not (1 <= limit <= 100 and offset >= 0):
        raise ValueError("limit must be between 1 and 100; offset must be nonnegative")

    # 2. 构造 select(CodeChunk)。
    # 必须通过 repository_id 限定查询范围。
    statement = select(CodeChunk).where(CodeChunk.repository_id == repository_id)

    # 3. file_path 不为 None 时，增加路径完全相等的条件。
    # 注意：使用 is not None，不是简单判断真假。
    if file_path is not None:
        statement = statement.where(CodeChunk.file_path == file_path)

    # 4. 设置稳定的排序：
    # file_path、start_line、id，均为升序
    statement = statement.order_by(CodeChunk.file_path, CodeChunk.start_line, CodeChunk.id)

    # 5. 添加分页。
    # 提示：statement.limit(limit).offset(offset)
    # 记得保存返回的新语句。
    statement = statement.limit(limit).offset(offset)

    # 6. 执行查询，返回 ORM 对象列表。
    # 可参考已有的 list_repository_files。
    return list(session.scalars(statement).all())

# 查询一批待处理代码块
def list_chunks_needing_embedding(
    session: Session,
    *,
    repository_id: UUID,
    model: str,
) -> list[CodeChunk]:
    # 1. select(CodeChunk)，限定 repository_id。
    statement = select(CodeChunk).where(CodeChunk.repository_id == repository_id)

    # 2. 再增加以下三个条件的“或”组合：
    # embedding 为空
    # embedding_model 为空
    # embedding_model 与 model 不同
    statement = statement.where(
        or_(
            CodeChunk.embedding.is_(None),
            CodeChunk.embedding_model.is_(None),
            CodeChunk.embedding_model != model,
        )
    )

    # 3. 按 file_path、start_line、id 排序，limit(10)。
    statement = statement.order_by(CodeChunk.file_path, CodeChunk.start_line, CodeChunk.id).limit(10)

    # 4. 返回 ORM 对象列表。
    return list(session.scalars(statement).all())

# 查询最相近的代码块
def search_code_chunks(
    session: Session,
    *,
    repository_id: UUID,
    query_vector: list[float],
    model: str,
    top_k: int = 5,
) -> list[tuple[CodeChunk, float]]:
    # 1. 校验 1 <= top_k <= 20。
    # 校验 query_vector 长度为 1024
    if not (1 <= top_k <= 20 and len(query_vector) == 1024):
        raise ValueError("top_k must be between 1 and 20, query_vector must be 1024")

    # 2. 构造距离表达式。这一步只是描述 SQL，不会立即执行。
    distance = CodeChunk.embedding.cosine_distance(
        query_vector
    ).label("distance")

    # 3. 同时查询 CodeChunk 和 distance。
    # 提示：select(CodeChunk, distance)
    statement = select(CodeChunk, distance)

    # 4. 添加三个 AND 条件：
    # 仓库 ID 匹配；
    # embedding 不为空，使用 .is_not(None)；
    # embedding_model 与 model 相同。
    statement = statement.where(
        CodeChunk.repository_id == repository_id,
        CodeChunk.embedding.is_not(None),
        CodeChunk.embedding_model == model
    )

    # 5. 按 distance 升序排列，CodeChunk.id 作为同距离时的排序依据。
    # 限制最多 top_k 条。
    statement = statement.order_by(distance, CodeChunk.id).limit(top_k)

    # 6. 使用 session.execute(statement).all()。
    # 遍历返回行，将 (chunk, float(distance_value)) 加入结果列表
    rows = session.execute(statement).all()
    result: list[tuple[CodeChunk, float]] = []

    for chunk, distance_value in rows:
        result.append((chunk, float(distance_value)))

    return result