"""auth_and_memberships

Revision ID: 91a2b3c4d5e6
Revises: 80f49ac7e2e2
Create Date: 2026-10-23 22:18:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '91a2b3c4d5e6'
down_revision: Union[str, None] = '80f49ac7e2e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_username'), ['username'], unique=True)

    op.create_table(
        'institution_memberships',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('institution_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['institution_id'], ['institutions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'institution_id', name='uq_user_institution_membership'),
    )
    with op.batch_alter_table('institution_memberships', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_institution_memberships_institution_id'), ['institution_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_institution_memberships_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('institution_memberships', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_institution_memberships_user_id'))
        batch_op.drop_index(batch_op.f('ix_institution_memberships_institution_id'))

    op.drop_table('institution_memberships')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_username'))

    op.drop_table('users')
