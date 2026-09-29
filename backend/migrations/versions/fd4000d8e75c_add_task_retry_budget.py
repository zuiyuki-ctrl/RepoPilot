"""add task retry budget

Revision ID: fd4000d8e75c
Revises: f94a414e578d
Create Date: 2026-09-29 16:29:20.956839

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd4000d8e75c'
down_revision: Union[str, Sequence[str], None] = 'f94a414e578d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_tasks",
        sa.Column(
            "retry_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "agent_tasks",
        sa.Column(
            "max_retries",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_tasks", "max_retries")
    op.drop_column("agent_tasks", "retry_count")