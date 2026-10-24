"""review_actions_and_finding_resolution

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-24 08:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add resolution and concurrency columns to findings
    with op.batch_alter_table('findings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('resolution_rationale', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('resolved_by', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))

    # 2. Add finding linkage, status transitions, and audit provenance to review_actions
    with op.batch_alter_table('review_actions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('finding_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('validation_run_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('actor_role', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('previous_status', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('new_status', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('rationale', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('request_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('evidence_ref', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('metadata_payload', sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            'fk_review_actions_finding_id',
            'findings',
            ['finding_id'],
            ['id'],
            ondelete='CASCADE',
        )
        batch_op.create_foreign_key(
            'fk_review_actions_validation_run_id',
            'validation_runs',
            ['validation_run_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index(batch_op.f('ix_review_actions_finding_id'), ['finding_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_review_actions_validation_run_id'), ['validation_run_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_review_actions_request_id'), ['request_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('review_actions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_review_actions_request_id'))
        batch_op.drop_index(batch_op.f('ix_review_actions_validation_run_id'))
        batch_op.drop_index(batch_op.f('ix_review_actions_finding_id'))
        batch_op.drop_constraint('fk_review_actions_validation_run_id', type_='foreignkey')
        batch_op.drop_constraint('fk_review_actions_finding_id', type_='foreignkey')
        batch_op.drop_column('metadata_payload')
        batch_op.drop_column('evidence_ref')
        batch_op.drop_column('request_id')
        batch_op.drop_column('rationale')
        batch_op.drop_column('new_status')
        batch_op.drop_column('previous_status')
        batch_op.drop_column('actor_role')
        batch_op.drop_column('validation_run_id')
        batch_op.drop_column('finding_id')

    with op.batch_alter_table('findings', schema=None) as batch_op:
        batch_op.drop_column('version')
        batch_op.drop_column('resolved_at')
        batch_op.drop_column('resolved_by')
        batch_op.drop_column('resolution_rationale')
