"""Durable, explicitly authorized Case draft authoring jobs (not a second catalog)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd1113a01b001'
down_revision = 'd719a02b0001'
branch_labels = depends_on = None


def upgrade():
    op.create_table('case_drafts',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('request_key', sa.UUID(), nullable=False, unique=True),
        sa.Column('request_sha256', sa.String(64), nullable=False),
        sa.Column('selection', postgresql.JSONB(), nullable=False),
        sa.Column('preview', postgresql.JSONB(), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('active_token', sa.UUID(), unique=True),
        sa.Column('text', postgresql.JSONB()), sa.Column('baseline', postgresql.JSONB()),
        sa.Column('observation', postgresql.JSONB()), sa.Column('error', postgresql.JSONB()),
        sa.Column('confirmed_benchmark_id', sa.UUID(), sa.ForeignKey('benchmark_versions.id')),
        sa.Column('confirmation', postgresql.JSONB()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('queued','validating','generating','ready','failed','interrupted','discarded','confirmed')",
                           name='ck_case_draft_status'))
    op.create_index('ix_case_drafts_status', 'case_drafts', ['status'])


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM case_drafts) THEN RAISE EXCEPTION 'Preserve draft evidence before downgrade'; END IF; END $$;")
    op.drop_index('ix_case_drafts_status', table_name='case_drafts')
    op.drop_table('case_drafts')
