from backend.app.db.models.repository import Repository
from backend.app.db.session import SessionLocal


def main():
    with SessionLocal.begin() as session:
        repository = Repository(
            name="repopilot-learning",
            source_path="D:/RepoPilot",
        )
        session.add(repository)
        session.flush()

        repository_id = repository.id
        print(f"Prepared repository: {repository_id}")

    # 上面的事务正常退出后已经提交。
    # 使用新的 Session，验证记录确实保存了。
    with SessionLocal() as session:
        saved = session.get(Repository, repository_id)

        assert saved is not None
        assert saved.language == "python"
        assert saved.status == "registered"
        assert saved.created_at is not None
        assert saved.indexed_at is None

        print(f"Loaded: {saved.name}")
        print(f"Language: {saved.language}, status: {saved.status}")


if __name__ == "__main__":
    main()