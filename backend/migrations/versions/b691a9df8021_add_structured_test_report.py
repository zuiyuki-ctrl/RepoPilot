"""Preserve bounded pytest JUnit evidence; historical rows remain NULL."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b691a9df8021"
down_revision = "fde182df4042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("test_runs", sa.Column("test_report", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("test_runs", "test_report")
