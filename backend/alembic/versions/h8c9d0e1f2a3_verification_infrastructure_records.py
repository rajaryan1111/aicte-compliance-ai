"""verification_infrastructure_records

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-10-29 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h8c9d0e1f2a3'
down_revision: Union[str, None] = 'g7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. verification_attempts
    op.create_table(
        'verification_attempts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('document_version_id', sa.Integer(), nullable=False),
        sa.Column('attempt_reference', sa.String(length=100), nullable=False),
        sa.Column('adapter_name', sa.String(length=100), nullable=False),
        sa.Column('source_title', sa.String(length=255), nullable=False),
        sa.Column('is_official_source', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='not_attempted', nullable=False),
        sa.Column('submitted_attributes', sa.Text(), nullable=True),
        sa.Column('returned_attributes', sa.Text(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('source_reference', sa.String(length=255), nullable=True),
        sa.Column('actor_id', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_version_id'], ['document_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('verification_attempts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_verification_attempts_attempt_reference'), ['attempt_reference'], unique=True)
        batch_op.create_index(batch_op.f('ix_verification_attempts_application_id'), ['application_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_verification_attempts_document_version_id'), ['document_version_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_verification_attempts_adapter_name'), ['adapter_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_verification_attempts_status'), ['status'], unique=False)

    # 2. institutional_record_snapshots
    op.create_table(
        'institutional_record_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('institution_id', sa.Integer(), nullable=False),
        sa.Column('record_type', sa.String(length=100), nullable=False),
        sa.Column('source_category', sa.String(length=50), server_default='unavailable', nullable=False),
        sa.Column('source_reference', sa.String(length=255), nullable=True),
        sa.Column('record_data', sa.Text(), nullable=False),
        sa.Column('limitations', sa.Text(), nullable=True),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['institution_id'], ['institutions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('institutional_record_snapshots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_institutional_record_snapshots_institution_id'), ['institution_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_institutional_record_snapshots_record_type'), ['record_type'], unique=False)

    # 3. infrastructure_evidence
    op.create_table(
        'infrastructure_evidence',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('document_version_id', sa.Integer(), nullable=False),
        sa.Column('evidence_type', sa.String(length=100), nullable=False),
        sa.Column('declared_area_sqm', sa.Float(), nullable=True),
        sa.Column('observed_area_sqm', sa.Float(), nullable=True),
        sa.Column('inspection_recommended', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('inspection_rationale', sa.Text(), nullable=True),
        sa.Column('analysis_metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_version_id'], ['document_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('infrastructure_evidence', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_infrastructure_evidence_application_id'), ['application_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_infrastructure_evidence_document_version_id'), ['document_version_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_infrastructure_evidence_evidence_type'), ['evidence_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_infrastructure_evidence_inspection_recommended'), ['inspection_recommended'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('infrastructure_evidence', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_infrastructure_evidence_inspection_recommended'))
        batch_op.drop_index(batch_op.f('ix_infrastructure_evidence_evidence_type'))
        batch_op.drop_index(batch_op.f('ix_infrastructure_evidence_document_version_id'))
        batch_op.drop_index(batch_op.f('ix_infrastructure_evidence_application_id'))
    op.drop_table('infrastructure_evidence')

    with op.batch_alter_table('institutional_record_snapshots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_institutional_record_snapshots_record_type'))
        batch_op.drop_index(batch_op.f('ix_institutional_record_snapshots_institution_id'))
    op.drop_table('institutional_record_snapshots')

    with op.batch_alter_table('verification_attempts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_verification_attempts_status'))
        batch_op.drop_index(batch_op.f('ix_verification_attempts_adapter_name'))
        batch_op.drop_index(batch_op.f('ix_verification_attempts_document_version_id'))
        batch_op.drop_index(batch_op.f('ix_verification_attempts_application_id'))
        batch_op.drop_index(batch_op.f('ix_verification_attempts_attempt_reference'))
    op.drop_table('verification_attempts')
