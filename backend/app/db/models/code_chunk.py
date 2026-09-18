from datetime import datetime
from uuid import UUID, uuid4
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Text,
    String,
    Integer,
    DateTime,
    func
)

from pgvector.sqlalchemy import VECTOR

from ..base import Base


# 代码块表：一行保存一个顶层函数或类的源码片段及其来源位置。
# 一个文件可以有零到多个块；块只是数据库记录，不会生成新的磁盘文件。
class CodeChunk(Base):
    __tablename__ = "code_chunks"

    __table_args__ = (
        CheckConstraint(
            "start_line >= 1",
            name="ck_code_chunks_start_line_positive"
        ),

        CheckConstraint(
            "end_line >= start_line",
            name="ck_code_chunks_line_range"
        )
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    # 同时记录仓库和文件归属，便于按仓库查询/清理；保存服务负责保持二者一致。
    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id"),
    )

    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("repository_files.id"),
    )

    # 冗余保存来源文件的相对路径，展示代码位置时可直接使用。
    file_path: Mapped[str] = mapped_column(Text)
    # symbol 是源码中的命名结构：当前支持函数（含 async）和类。
    symbol_name: Mapped[str] = mapped_column(Text)
    symbol_type: Mapped[str] = mapped_column(String(32))
    # 行号从 1 开始，首尾都包含；有装饰器时从装饰器所在行开始。
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    # 真正的代码文本；类方法/嵌套函数保留在外层块内，不单独拆块。
    content: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now()
    )

    # Python 属性叫 chunk_metadata，数据库列叫 metadata；当前默认 {}，未存向量。
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict
    )

    # 计算相似度
    embedding: Mapped[list[float] | None] = mapped_column(
        VECTOR(1024),
        nullable=True,
    )

    # 标明生成向量的模型
    embedding_model: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )