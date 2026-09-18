from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, String, DateTime, func

from ..base import Base

# 仓库登记表：一行代表一次注册及其独立工作副本，不保存源码正文。
# 同一个源目录可以注册多次；每次有独立的 id 和 workspace_path。
class Repository(Base):
    __tablename__ = 'repositories'

    id : Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4
    )

    name: Mapped[str] = mapped_column(String(255))
    # 用户提供的 Git 根目录；注册时检查已提交且工作区干净。
    source_path: Mapped[str] = mapped_column(Text)
    # 系统克隆的副本；scan/index 读取这里，不自动同步 source_path 的新提交。
    workspace_path: Mapped[str | None] = mapped_column(
        Text,
        nullable = True
    )

    git_branch: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )
    # 副本创建时的 Git 提交版本；与本表的 UUID 主键 id 含义不同。
    commit_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )
    language: Mapped[str] = mapped_column(
        String(16),
        default='python'
    )
    # 当前索引服务尚未推进此状态，索引成功后也可能仍是 registered。
    status: Mapped[str] = mapped_column(
        String(32),
        default='registered'
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    # 预留的索引完成时间；当前 index 流程尚未写入。
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
