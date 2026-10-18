"""Append-only human decisions bound to comparison snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'd716a06b0001'
down_revision = 'd715a05b0001'
branch_labels = depends_on = None


def upgrade():
    op.create_table('experiment_reviews',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('experiment_id', sa.Uuid(), sa.ForeignKey('platform_experiments.id'), nullable=False),
        sa.Column('request_key', sa.Uuid(), unique=True, nullable=False),
        sa.Column('request_sha256', sa.String(64), nullable=False),
        sa.Column('comparison_sha256', sa.String(64), nullable=False),
        sa.Column('snapshot', JSONB(), nullable=False),
        sa.Column('reviewer', sa.String(100), nullable=False),
        sa.Column('action', sa.String(32), nullable=False),
        sa.Column('rationale', sa.String(2000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_experiment_reviews_experiment_id', 'experiment_reviews', ['experiment_id'])


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM experiment_reviews) THEN RAISE EXCEPTION 'Preserve reviews before downgrade'; END IF; END $$;")
    op.drop_table('experiment_reviews')
