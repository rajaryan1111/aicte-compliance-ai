"""create_processing_jobs_and_outbox

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-24 07:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create processing_jobs table
    op.create_table(
        'processing_jobs',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('document_version_id', sa.Integer(), nullable=False),
        sa.Column('job_type', sa.String(length=64), server_default='document_intake_pipeline', nullable=False),
        sa.Column('state', sa.String(length=32), server_default='queued', nullable=False),
        sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_attempts', sa.Integer(), server_default='3', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_code', sa.String(length=64), nullable=True),
        sa.Column('pipeline_version', sa.String(length=32), server_default='v1.0', nullable=True),
        sa.ForeignKeyConstraint(['document_version_id'], ['document_versions.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('document_version_id', 'job_type', name='uq_processing_job_version_type')
    )
    op.create_index(op.f('ix_processing_jobs_document_version_id'), 'processing_jobs', ['document_version_id'], unique=False)
    op.create_index(op.f('ix_processing_jobs_state'), 'processing_jobs', ['state'], unique=False)

    # 2. Create outbox_messages table
    op.create_table(
        'outbox_messages',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('topic', sa.String(length=64), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='pending', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
    )
    op.create_index(op.f('ix_outbox_messages_topic'), 'outbox_messages', ['topic'], unique=False)
    op.create_index(op.f('ix_outbox_messages_status'), 'outbox_messages', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_outbox_messages_status'), table_name='outbox_messages')
    op.drop_index(op.f('ix_outbox_messages_topic'), table_name='outbox_messages')
    op.drop_table('outbox_messages')

    op.drop_index(op.f('ix_processing_jobs_state'), table_name='processing_jobs')
    op.drop_index(op.f('ix_processing_jobs_document_version_id'), table_name='processing_jobs')
    op.drop_table('processing_jobs')
