"""Frozen experiments and persistent preparation queue."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = 'd715a05b0001'
down_revision = 'd715a04b0001'
branch_labels = depends_on = None


def upgrade():
    op.create_table('platform_experiments',
        sa.Column('id',sa.Uuid(),primary_key=True), sa.Column('request_key',sa.Uuid(),unique=True,nullable=False),
        sa.Column('request_sha256',sa.String(64),nullable=False), sa.Column('manifest_sha256',sa.String(64),nullable=False),
        sa.Column('manifest',JSONB(),nullable=False), sa.Column('cancel_requested',sa.Boolean(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_table('experiment_members',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('experiment_id',sa.Uuid(),sa.ForeignKey('platform_experiments.id'),nullable=False),
        sa.Column('sequence',sa.Integer(),nullable=False), sa.Column('case_index',sa.Integer(),nullable=False),
        sa.Column('repetition',sa.Integer(),nullable=False),sa.Column('arm',sa.String(16),nullable=False),
        sa.Column('status',sa.String(32),nullable=False),sa.Column('active_token',sa.Uuid(),unique=True),
        sa.Column('run_id',sa.Uuid(),sa.ForeignKey('platform_runs.id'),unique=True),sa.Column('error_code',sa.String(100)),
        sa.Column('claimed_at',sa.DateTime(timezone=True)),
        sa.UniqueConstraint('experiment_id','sequence',name='uq_experiment_member_sequence'))
    op.create_index('ix_experiment_members_experiment_id','experiment_members',['experiment_id'])


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM platform_experiments) THEN RAISE EXCEPTION 'Preserve experiments before downgrade'; END IF; END $$;")
    op.drop_table('experiment_members')
    op.drop_table('platform_experiments')
