from logging.config import fileConfig

from alembic import context

from backend.app.db.base import Base
from backend.app.db.models.repository import Repository
from backend.app.db.session import engine
from backend.app.db.models.repository_file import RepositoryFile
from backend.app.db.models.code_chunk import CodeChunk
from backend.app.db.models.agent_task import AgentTask
from backend.app.db.models.task_event import TaskEvent


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=engine.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()