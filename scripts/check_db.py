from sqlalchemy import text

from backend.app.db.session import engine

def main():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar_one()
        print(f"Database connection OK, result={result}")


if __name__ == "__main__":
    main()