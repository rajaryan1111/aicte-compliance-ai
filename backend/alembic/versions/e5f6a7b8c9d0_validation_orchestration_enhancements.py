"""validation_orchestration_enhancements

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-24 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add provenance, outcome, and summary columns to validation_runs
    with op.batch_alter_table('validation_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('outcome', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('consumed_version_ids', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('rule_snapshot', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('summary_counts', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('limitations', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_validation_runs_outcome'), ['outcome'], unique=False)

    # 2. Create validation_check_results table
    op.create_table(
        'validation_check_results',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True, nullable=False),
        sa.Column('validation_run_id', sa.Integer(), nullable=False),
        sa.Column('check_id', sa.String(length=100), nullable=False),
        sa.Column('check_name', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('document_version_id', sa.Integer(), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=True),
        sa.Column('limitations', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['validation_run_id'], ['validation_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_version_id'], ['document_versions.id'], ondelete='SET NULL'),
    )
    op.create_index(op.f('ix_validation_check_results_validation_run_id'), 'validation_check_results', ['validation_run_id'], unique=False)
    op.create_index(op.f('ix_validation_check_results_check_id'), 'validation_check_results', ['check_id'], unique=False)
    op.create_index(op.f('ix_validation_check_results_status'), 'validation_check_results', ['status'], unique=False)
    op.create_index(op.f('ix_validation_check_results_document_version_id'), 'validation_check_results', ['document_version_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_validation_check_results_document_version_id'), table_name='validation_check_results')
    op.drop_index(op.f('ix_validation_check_results_status'), table_name='validation_check_results')
    op.drop_index(op.f('ix_validation_check_results_check_id'), table_name='validation_check_results')
    op.drop_index(op.f('ix_validation_check_results_validation_run_id'), table_name='validation_check_results')
    op.drop_table('validation_check_results')

    with op.batch_alter_table('validation_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_validation_runs_outcome'))
        batch_op.drop_column('limitations')
        batch_op.drop_column('summary_counts')
        batch_op.drop_column('rule_snapshot')
        batch_op.drop_column('consumed_version_ids')
        batch_op.drop_column('outcome')
