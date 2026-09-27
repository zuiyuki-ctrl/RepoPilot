from sqlalchemy import text

from backend.app.db.session import engine

# 执行 SELECT 1 检查数据库连接，供开发环境排障；不验证业务表和迁移。
def main():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar_one()
        print(f"Database connection OK, result={result}")


if __name__ == "__main__":
    main()