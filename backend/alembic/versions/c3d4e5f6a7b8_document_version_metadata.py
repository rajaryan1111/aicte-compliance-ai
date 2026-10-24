"""document_version_metadata

Revision ID: c3d4e5f6a7b8
Revises: 91a2b3c4d5e6
Create Date: 2026-10-23 22:33:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = '91a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('document_versions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('file_name', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('scan_status', sa.String(length=50), nullable=True, server_default='pending_scan'))


def downgrade() -> None:
    with op.batch_alter_table('document_versions', schema=None) as batch_op:
        batch_op.drop_column('scan_status')
        batch_op.drop_column('file_name')
