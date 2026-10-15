"""Immutable Agent/Benchmark versions and persistent validation jobs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'd715a04b0001'
down_revision = 'd714a02b0001'
branch_labels = depends_on = None


def upgrade():
    for table, label in [('agent_versions', 'agent'), ('benchmark_versions', 'benchmark')]:
        op.create_table(table,
            sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('version', sa.String(100), nullable=False),
            sa.Column('content_sha256', sa.String(64), nullable=False),
            sa.Column('descriptor', JSONB(), nullable=False),
            sa.Column('status', sa.String(32), nullable=False),
            sa.Column('validation', JSONB()),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint('name', 'version', name=f'uq_{label}_version_label'))
    op.create_table('catalog_validations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('request_key', sa.Uuid(), unique=True, nullable=False),
        sa.Column('agent_version_id', sa.Uuid(), sa.ForeignKey('agent_versions.id')),
        sa.Column('benchmark_version_id', sa.Uuid(), sa.ForeignKey('benchmark_versions.id')),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('active_token', sa.Uuid(), unique=True),
        sa.Column('report', JSONB()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('(agent_version_id IS NOT NULL) <> (benchmark_version_id IS NOT NULL)', name='ck_catalog_validation_owner'),
        sa.CheckConstraint("status IN ('queued','running','passed','failed','interrupted')", name='ck_catalog_validation_status'))
    for field in ('agent_version_id', 'benchmark_version_id'):
        op.create_index('ix_catalog_validations_' + field, 'catalog_validations', [field])


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM agent_versions) OR EXISTS (SELECT 1 FROM benchmark_versions)
        THEN RAISE EXCEPTION 'Preserve catalog history before downgrade'; END IF; END $$;""")
    for table in ('catalog_validations', 'benchmark_versions', 'agent_versions'):
        op.drop_table(table)
