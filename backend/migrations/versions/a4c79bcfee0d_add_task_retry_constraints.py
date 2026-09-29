"""add task retry constraints

Revision ID: a4c79bcfee0d
Revises: fd4000d8e75c
Create Date: 2026-09-29 16:40:03.045692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c79bcfee0d'
down_revision: Union[str, Sequence[str], None] = 'fd4000d8e75c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_agent_tasks_retry_count_nonnegative",
        "agent_tasks",
        "retry_count >= 0",
    )
    op.create_check_constraint(
        "ck_agent_tasks_max_retries_range",
        "agent_tasks",
        "max_retries >= 0 AND max_retries <= 3",
    )
    op.create_check_constraint(
        "ck_agent_tasks_retry_budget",
        "agent_tasks",
        "retry_count <= max_retries",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_tasks_retry_budget",
        "agent_tasks",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_tasks_max_retries_range",
        "agent_tasks",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_tasks_retry_count_nonnegative",
        "agent_tasks",
        type_="check",
    )

