"""Durable worker cursor and approval checkpoints.

Revision ID: d714a02b0001
Revises: d714a01b0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = 'd714a02b0001'
down_revision = 'd714a01b0001'
branch_labels = depends_on = None


def upgrade():
    op.create_table('run_work',
        sa.Column('run_id', sa.Uuid(), sa.ForeignKey('platform_runs.id'), primary_key=True),
        sa.Column('stage', sa.String(32), nullable=False),
        sa.Column('state', pg.JSONB(), nullable=False),
        sa.Column('ready', sa.Boolean(), nullable=False),
        sa.Column('cancel_requested', sa.Boolean(), nullable=False),
        sa.Column('active_token', sa.Uuid(), unique=True),
        sa.Column('active_since', sa.DateTime(timezone=True)),
        sa.Column('active_seconds', sa.Float(), nullable=False),
        sa.Column('result', pg.JSONB()),
        sa.Column('cleanup_status', sa.String(32), nullable=False),
        sa.Column('error_code', sa.String(100)),
        sa.Column('legacy_cursor', sa.Integer(), nullable=False),
        sa.CheckConstraint('active_seconds >= 0', name='ck_run_work_seconds'))
    op.create_table('run_checkpoints',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('run_id', sa.Uuid(), sa.ForeignKey('platform_runs.id'), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('run_version', sa.Integer(), nullable=False),
        sa.Column('payload', pg.JSONB(), nullable=False),
        sa.Column('payload_sha256', sa.String(64), nullable=False),
        sa.Column('decision', sa.String(16)),
        sa.Column('comment', sa.String(1000)),
        sa.Column('decided_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('plan','candidate')", name='ck_run_checkpoint_kind'),
        sa.CheckConstraint("decision IS NULL OR decision IN ('approved','rejected')", name='ck_run_checkpoint_decision'))
    op.create_index('ix_run_checkpoints_run_id', 'run_checkpoints', ['run_id'])


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM run_work) OR EXISTS (SELECT 1 FROM run_checkpoints)
        THEN RAISE EXCEPTION 'Preserve v2 worker and approval history before downgrade'; END IF; END $$;""")
    op.drop_table('run_checkpoints')
    op.drop_table('run_work')
