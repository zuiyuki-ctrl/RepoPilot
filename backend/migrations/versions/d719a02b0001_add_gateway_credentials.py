"""Opaque attempt credentials and explicit mock provenance; no plaintext secrets."""
from alembic import op
import sqlalchemy as sa

revision = 'd719a02b0001'
down_revision = 'd719a01b0001'
branch_labels = depends_on = None


def upgrade():
    op.add_column('run_model_grants', sa.Column('credential_sha256', sa.String(64), nullable=True))
    op.add_column('run_model_grants', sa.Column('gateway_mode', sa.String(16), nullable=True))
    op.create_unique_constraint('uq_run_model_grants_credential', 'run_model_grants', ['credential_sha256'])
    op.add_column('model_calls', sa.Column('transport', sa.String(16), nullable=True))


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM run_model_grants WHERE credential_sha256 IS NOT NULL OR gateway_mode IS NOT NULL) OR EXISTS (SELECT 1 FROM model_calls WHERE transport IS NOT NULL) THEN RAISE EXCEPTION 'Preserve gateway authorization and provenance before downgrade'; END IF; END $$;")
    op.drop_column('model_calls', 'transport')
    op.drop_constraint('uq_run_model_grants_credential', 'run_model_grants', type_='unique')
    op.drop_column('run_model_grants', 'gateway_mode')
    op.drop_column('run_model_grants', 'credential_sha256')
