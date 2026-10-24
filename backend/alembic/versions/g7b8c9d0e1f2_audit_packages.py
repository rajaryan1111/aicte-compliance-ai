"""audit_packages

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-24 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_packages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('package_reference', sa.String(length=100), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('validation_run_id', sa.Integer(), nullable=True),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='completed', nullable=False),
        sa.Column('sha256_root_hash', sa.String(length=64), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(length=500), nullable=True),
        sa.Column('manifest_json', sa.Text(), nullable=False),
        sa.Column('generated_by', sa.String(length=100), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['validation_run_id'], ['validation_runs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('audit_packages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_packages_package_reference'), ['package_reference'], unique=True)
        batch_op.create_index(batch_op.f('ix_audit_packages_application_id'), ['application_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_packages_validation_run_id'), ['validation_run_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_packages_status'), ['status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('audit_packages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_packages_status'))
        batch_op.drop_index(batch_op.f('ix_audit_packages_validation_run_id'))
        batch_op.drop_index(batch_op.f('ix_audit_packages_application_id'))
        batch_op.drop_index(batch_op.f('ix_audit_packages_package_reference'))
    op.drop_table('audit_packages')
