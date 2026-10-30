"""rule_approvals_and_retention

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-10-30 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i9d0e1f2a3b4'
down_revision: Union[str, None] = 'h8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. rule_approvals table
    op.create_table(
        'rule_approvals',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rule_id', sa.String(length=100), nullable=False),
        sa.Column('rule_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('status', sa.String(length=50), server_default='active', nullable=False),
        sa.Column('decision', sa.String(length=50), nullable=False),
        sa.Column('reviewer_id', sa.String(length=100), nullable=False),
        sa.Column('reviewer_username', sa.String(length=100), nullable=False),
        sa.Column('reviewer_role', sa.String(length=50), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('source_title', sa.String(length=255), nullable=False),
        sa.Column('source_clause', sa.String(length=120), nullable=False),
        sa.Column('source_page', sa.String(length=40), nullable=False),
        sa.Column('source_document_version', sa.String(length=120), nullable=False),
        sa.Column('source_document_sha256', sa.String(length=64), nullable=True),
        sa.Column('source_retrieved_at', sa.Date(), nullable=False),
        sa.Column('source_verified_by', sa.String(length=120), nullable=False),
        sa.Column('source_verified_at', sa.Date(), nullable=False),
        sa.Column('source_verification_status', sa.String(length=50), server_default='verified', nullable=False),
        sa.Column('statutory_interpretation_approved', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('rule_definition_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rule_id', 'rule_version', 'decision', name='uq_rule_approval_version_decision'),
    )
    with op.batch_alter_table('rule_approvals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_rule_approvals_rule_id'), ['rule_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_rule_approvals_status'), ['status'], unique=False)

    # 2. retention_runs table
    op.create_table(
        'retention_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_reference', sa.String(length=100), nullable=False),
        sa.Column('execution_type', sa.String(length=50), nullable=False),
        sa.Column('dry_run', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='running', nullable=False),
        sa.Column('quarantined_purged_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('jobs_cleaned_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('storage_errors_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('triggered_by', sa.String(length=100), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('retention_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_retention_runs_run_reference'), ['run_reference'], unique=True)
        batch_op.create_index(batch_op.f('ix_retention_runs_status'), ['status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('retention_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_retention_runs_status'))
        batch_op.drop_index(batch_op.f('ix_retention_runs_run_reference'))
    op.drop_table('retention_runs')

    with op.batch_alter_table('rule_approvals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rule_approvals_status'))
        batch_op.drop_index(batch_op.f('ix_rule_approvals_rule_id'))
    op.drop_table('rule_approvals')
