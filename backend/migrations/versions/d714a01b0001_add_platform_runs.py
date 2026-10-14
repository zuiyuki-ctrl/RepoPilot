"""v2 Run / event / evaluation ownership; keep legacy task tests intact."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = 'd714a01b0001'
down_revision = 'b691a9df8021'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('platform_runs',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('repository_id', sa.Uuid(), sa.ForeignKey('repositories.id'), nullable=False),
        sa.Column('legacy_task_id', sa.Uuid(), sa.ForeignKey('agent_tasks.id'), unique=True),
        sa.Column('creation_key', sa.String(100), nullable=False, unique=True),
        sa.Column('request_sha256', sa.String(64), nullable=False),
        sa.Column('request', pg.JSONB(), nullable=False),
        sa.Column('lifecycle', sa.String(32), nullable=False),
        sa.Column('execution_status', sa.String(32), nullable=False),
        sa.Column('evaluation_outcome', sa.String(32), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('event_sequence', sa.Integer(), nullable=False),
        sa.Column('capabilities', pg.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("lifecycle IN ('queued','preparing','running','awaiting_input','evaluating','finished','interrupted')", name='ck_platform_runs_lifecycle'),
        sa.CheckConstraint("execution_status IN ('pending','completed','failed','timed_out','cancelled','unknown')", name='ck_platform_runs_execution'),
        sa.CheckConstraint("evaluation_outcome IN ('pending','passed','not_passed','unknown')", name='ck_platform_runs_evaluation'),
        sa.CheckConstraint('version >= 1 AND event_sequence >= 0', name='ck_platform_runs_counters'),
        sa.CheckConstraint("(lifecycle IN ('finished','interrupted')) = (completed_at IS NOT NULL)", name='ck_platform_runs_terminal_time'),
        sa.CheckConstraint("evaluation_outcome != 'passed' OR (execution_status = 'completed' AND lifecycle = 'finished')", name='ck_platform_runs_passed'))
    op.create_index('ix_platform_runs_repository_id', 'platform_runs', ['repository_id'])
    op.create_table('platform_run_events',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('run_id', sa.Uuid(), sa.ForeignKey('platform_runs.id'), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('source', sa.String(32), nullable=False),
        sa.Column('payload', pg.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('run_id', 'sequence', name='uq_platform_run_events_sequence'),
        sa.CheckConstraint('sequence > 0', name='ck_platform_run_events_sequence'),
        sa.CheckConstraint("source IN ('platform','adapter','agent_reported')", name='ck_platform_run_events_source'))
    op.create_index('ix_platform_run_events_run_id', 'platform_run_events', ['run_id'])
    op.add_column('test_runs', sa.Column('run_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('fk_test_runs_platform_run', 'test_runs', 'platform_runs', ['run_id'], ['id'])
    op.create_index('ix_test_runs_run_id', 'test_runs', ['run_id'])
    op.alter_column('test_runs', 'task_id', existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint('ck_test_runs_single_owner', 'test_runs', '(task_id IS NOT NULL) <> (run_id IS NOT NULL)')
    op.create_table('run_evaluations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('run_id', sa.Uuid(), sa.ForeignKey('platform_runs.id'), nullable=False),
        sa.Column('test_run_id', sa.Uuid(), sa.ForeignKey('test_runs.id')),
        sa.Column('evidence_sha256', sa.String(64), nullable=False),
        sa.Column('rule_sha256', sa.String(64), nullable=False),
        sa.Column('outcome', sa.String(32), nullable=False),
        sa.Column('reason', sa.String(100), nullable=False),
        sa.Column('evidence', pg.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('run_id', 'evidence_sha256', name='uq_run_evaluations_evidence'),
        sa.CheckConstraint("outcome IN ('passed','not_passed','unknown')", name='ck_run_evaluations_outcome'))
    op.create_index('ix_run_evaluations_run_id', 'run_evaluations', ['run_id'])


def downgrade():
    # 拒绝把新 Run 的测试变成无主记录；不能为了回滚删除真实证据。
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM test_runs WHERE run_id IS NOT NULL) "
               "OR EXISTS (SELECT 1 FROM platform_runs) THEN "
               "RAISE EXCEPTION 'v2 run data exists; archive and plan a data migration before downgrade'; END IF; END $$")
    op.drop_table('run_evaluations')
    op.drop_constraint('ck_test_runs_single_owner', 'test_runs', type_='check')
    op.alter_column('test_runs', 'task_id', existing_type=sa.Uuid(), nullable=False)
    op.drop_index('ix_test_runs_run_id', table_name='test_runs')
    op.drop_constraint('fk_test_runs_platform_run', 'test_runs', type_='foreignkey')
    op.drop_column('test_runs', 'run_id')
    op.drop_table('platform_run_events')
    op.drop_table('platform_runs')
