"""remediation_plans

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-10-31 09:00:00.000000

Adds the institution-scoped remediation plan and its tasks. Purely additive: no existing table,
column or constraint is altered, so a deployment can be rolled back by dropping these two tables
without touching application, validation or audit data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j0e1f2a3b4c5'
down_revision: Union[str, None] = 'i9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'remediation_plans',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('institution_id', sa.Integer(), nullable=False),
        sa.Column('plan_key', sa.String(length=64), nullable=False),
        sa.Column('application_type', sa.String(length=50), nullable=False),
        sa.Column('deadline_policy', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=100), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['institution_id'], ['institutions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('institution_id', 'plan_key', name='uq_remediation_plan_institution_key'),
    )
    op.create_index('ix_remediation_plans_institution_id', 'remediation_plans', ['institution_id'])
    op.create_index('ix_remediation_plans_plan_key', 'remediation_plans', ['plan_key'])

    op.create_table(
        'remediation_tasks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('task_key', sa.String(length=160), nullable=False),
        sa.Column('document_id', sa.String(length=100), nullable=False),
        sa.Column('document_label', sa.String(length=255), nullable=False),
        sa.Column('finding_code', sa.String(length=40), nullable=False),
        sa.Column('priority', sa.String(length=10), nullable=False),
        sa.Column('owner_role', sa.String(length=120), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('evidence_required', sa.Text(), nullable=False),
        sa.Column('clause', sa.String(length=80), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='open', nullable=False),
        sa.Column('note', sa.String(length=280), server_default='', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('status_changed_by', sa.String(length=100), nullable=True),
        sa.Column('status_changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['plan_id'], ['remediation_plans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('plan_id', 'task_key', name='uq_remediation_task_plan_key'),
    )
    op.create_index('ix_remediation_tasks_plan_id', 'remediation_tasks', ['plan_id'])
    op.create_index('ix_remediation_tasks_status', 'remediation_tasks', ['status'])


def downgrade() -> None:
    op.drop_index('ix_remediation_tasks_status', table_name='remediation_tasks')
    op.drop_index('ix_remediation_tasks_plan_id', table_name='remediation_tasks')
    op.drop_table('remediation_tasks')
    op.drop_index('ix_remediation_plans_plan_key', table_name='remediation_plans')
    op.drop_index('ix_remediation_plans_institution_id', table_name='remediation_plans')
    op.drop_table('remediation_plans')
