from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import sessionmaker

from ..core.config import (
    DB_HOST,
    DB_PORT,
    DB_NAME ,
    DB_USER,
    DB_PASSWORD,
)

url = URL.create(
    drivername="postgresql+psycopg",
    database=DB_NAME,
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
)

# Engine 管理连接池；Session 是一次业务操作使用的数据库会话，不是全局共享事务。
engine = create_engine(url, connect_args={"connect_timeout": 5})

'''
使用现有的 engine。
通过 with engine.connect() 取得连接。
执行 SELECT 1。
失败时让异常向调用方传递，不在这里转换成 HTTP 响应。
'''
# 仅验证能连接并执行 SELECT 1，不检查业务表或迁移版本；供 /ready 使用。
def check_database_connection() -> None:
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))

# SessionLocal 是创建 Session 的工厂。后续每次操作按需创建 Session，不把一个全局 Session 给所有请求共用
# with SessionLocal.begin() 正常结束自动提交，异常则回滚；仅 flush 不会提交事务。
SessionLocal  = sessionmaker(bind=engine)

