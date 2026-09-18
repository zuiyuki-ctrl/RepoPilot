from datetime import datetime
from uuid import UUID, uuid4
from ..base import Base


from sqlalchemy import (
    UniqueConstraint,
    CheckConstraint,
    ForeignKey,
    Text,
    String,
    BigInteger,
    DateTime,
    func
)

from sqlalchemy.orm import Mapped, mapped_column

# 文件登记表：一行描述某仓库中的一个文件，保存元数据，不保存完整源码。
# repository_id + path 唯一；不同仓库可以各自拥有同名文件。
class RepositoryFile(Base):
    __tablename__ = "repository_files"

    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "path",
            name="uq_repository_files_repository_path",
        ),
        CheckConstraint(
            "size >= 0",
            name="ck_repository_files_size_nonnegative",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    # 外键指向所属仓库；本文件的代码块通过 code_chunks.file_id 关联回来。
    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id"),
    )

    # 相对于 workspace_path 的路径，统一使用 /，例如 pkg/helpers.py。
    path: Mapped[str] = mapped_column(Text)

    language: Mapped[str] = mapped_column(String(32))

    # 原始文件字节的 SHA-256 指纹，用于判断元数据变化，不是 Git commit hash。
    file_hash: Mapped[str] = mapped_column(String(64))

    # 单位是字节，不是字符数或代码行数。
    size: Mapped[int] = mapped_column(BigInteger)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
