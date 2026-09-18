from sqlalchemy.orm import DeclarativeBase

# 所有 ORM 表模型的共同基类；Base.metadata 汇总表结构，供 Alembic 迁移使用。
class Base(DeclarativeBase):
    ...

