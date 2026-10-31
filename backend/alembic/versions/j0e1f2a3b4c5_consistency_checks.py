"""Persist institution-scoped consistency checks and findings.

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-10-31 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j0e1f2a3b4c5"
down_revision: str | None = "i9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consistency_checks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("check_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("related_field", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("consistency_checks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_consistency_checks_application_id"),
            ["application_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_consistency_checks_status"), ["status"], unique=False
        )

    op.create_table(
        "consistency_findings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("consistency_check_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("value_1", sa.Text(), nullable=False),
        sa.Column("value_2", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["consistency_check_id"],
            ["consistency_checks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("consistency_findings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_consistency_findings_consistency_check_id"),
            ["consistency_check_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_consistency_findings_resolved"),
            ["resolved"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("consistency_findings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_consistency_findings_resolved"))
        batch_op.drop_index(
            batch_op.f("ix_consistency_findings_consistency_check_id")
        )
    op.drop_table("consistency_findings")

    with op.batch_alter_table("consistency_checks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_consistency_checks_status"))
        batch_op.drop_index(batch_op.f("ix_consistency_checks_application_id"))
    op.drop_table("consistency_checks")
