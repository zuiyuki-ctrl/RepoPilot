"""Run-scoped model authorization and durable call idempotency."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'd719a01b0001'
down_revision = 'd716a06b0001'
branch_labels = depends_on = None


def upgrade():
    op.create_table('run_model_grants',
        sa.Column('run_id', sa.Uuid(), sa.ForeignKey('platform_runs.id'), primary_key=True),
        sa.Column('config_sha256', sa.String(64), nullable=False),
        sa.Column('policy', JSONB(), nullable=False),
        sa.Column('calls_reserved', sa.Integer(), nullable=False),
        sa.Column('known_total_tokens', sa.Integer(), nullable=False),
        sa.Column('worker_token', sa.Uuid()),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('stop_reason', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('calls_reserved >= 0 AND known_total_tokens >= 0', name='ck_model_grant_counters'),
        sa.CheckConstraint('(worker_token IS NULL) = (expires_at IS NULL)', name='ck_model_grant_attempt'))
    op.create_table('model_calls',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('run_id', sa.Uuid(), sa.ForeignKey('run_model_grants.run_id'), nullable=False),
        sa.Column('call_id', sa.String(64), nullable=False),
        sa.Column('worker_token', sa.Uuid(), nullable=False),
        sa.Column('request_sha256', sa.String(64), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=False),
        sa.Column('usage', JSONB()),
        sa.Column('result_sha256', sa.String(64)),
        sa.Column('error_code', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('dispatched_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('run_id', 'call_id', name='uq_model_call_idempotency'),
        sa.CheckConstraint("status IN ('reserved','dispatched','succeeded','failed','unknown')", name='ck_model_call_status'))
    op.create_index('ix_model_calls_run_id', 'model_calls', ['run_id'])
    op.create_index('uq_model_call_inflight', 'model_calls', ['run_id'], unique=True,
                    postgresql_where=sa.text("status IN ('reserved','dispatched')"))


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM run_model_grants) OR EXISTS (SELECT 1 FROM model_calls) THEN RAISE EXCEPTION 'Preserve model authorization and call evidence before downgrade'; END IF; END $$;")
    op.drop_table('model_calls')
    op.drop_table('run_model_grants')
