"""remediation_deadline_changes

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-10-31 15:40:00.000000

Adds the append-only schedule-change history for institution remediation plans.

This is a separate revision rather than an edit to j0e1f2a3b4c5 on purpose: any database that
already applied the plan revision must be able to upgrade in place, and Alembic will not re-run an
applied revision. The change is additive; downgrade drops only the history table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k1f2a3b4c5d6'
down_revision: Union[str, None] = 'j0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'remediation_deadline_changes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('changed_by', sa.String(length=100), nullable=False),
        sa.Column('previous_policy', sa.Text(), nullable=False),
        sa.Column('new_policy', sa.Text(), nullable=False),
        sa.Column('rescheduled_tasks', sa.Integer(), server_default='0', nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['plan_id'], ['remediation_plans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_remediation_deadline_changes_plan_id', 'remediation_deadline_changes', ['plan_id']
    )


def downgrade() -> None:
    op.drop_index(
        'ix_remediation_deadline_changes_plan_id', table_name='remediation_deadline_changes'
    )
    op.drop_table('remediation_deadline_changes')
