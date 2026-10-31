"""Add requirement-scoped evidence mapping and assessment history.

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "k1f2a3b4c5d6"
down_revision = "j0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "requirement_evidence_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("rule_approval_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("extracted_field_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="suggested"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="user"),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("reviewed_by", sa.String(length=100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_approval_id"], ["rule_approvals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["extracted_field_id"], ["extracted_fields.id"], ondelete="SET NULL"),
    )
    for column in ("application_id", "rule_approval_id", "document_version_id", "extracted_field_id", "status"):
        op.create_index(f"ix_requirement_evidence_mappings_{column}", "requirement_evidence_mappings", [column])

    op.create_table(
        "requirement_assessments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("validation_run_id", sa.Integer(), nullable=False),
        sa.Column("rule_approval_id", sa.Integer(), nullable=False),
        sa.Column("applicability_status", sa.String(length=40), nullable=False),
        sa.Column("applicability_reason", sa.Text(), nullable=False),
        sa.Column("evaluation_status", sa.String(length=40), nullable=False),
        sa.Column("outcome_status", sa.String(length=40), nullable=False),
        sa.Column("evidence_sufficiency", sa.String(length=40), nullable=False),
        sa.Column("result_message", sa.Text(), nullable=False),
        sa.Column("source_snapshot", sa.Text(), nullable=False),
        sa.Column("evidence_snapshot", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.String(length=100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["validation_run_id"], ["validation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_approval_id"], ["rule_approvals.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("validation_run_id", "rule_approval_id", name="uq_requirement_assessment_run_rule"),
    )
    for column in ("application_id", "validation_run_id", "rule_approval_id", "applicability_status", "outcome_status", "evidence_sufficiency", "review_status"):
        op.create_index(f"ix_requirement_assessments_{column}", "requirement_assessments", [column])

    op.create_table(
        "requirement_assessment_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("requirement_assessment_id", sa.Integer(), nullable=False),
        sa.Column("mapping_id", sa.Integer(), nullable=True),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("extracted_field_id", sa.Integer(), nullable=True),
        sa.Column("mapping_status", sa.String(length=32), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("evidence_sufficiency", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["requirement_assessment_id"], ["requirement_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mapping_id"], ["requirement_evidence_mappings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["extracted_field_id"], ["extracted_fields.id"], ondelete="SET NULL"),
    )
    for column in ("requirement_assessment_id", "mapping_id", "document_version_id", "extracted_field_id"):
        op.create_index(f"ix_requirement_assessment_evidence_{column}", "requirement_assessment_evidence", [column])

    op.create_table(
        "finding_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("finding_id", sa.Integer(), nullable=False),
        sa.Column("assessment_evidence_id", sa.Integer(), nullable=True),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("extracted_field_id", sa.Integer(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("evidence_role", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessment_evidence_id"], ["requirement_assessment_evidence.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["extracted_field_id"], ["extracted_fields.id"], ondelete="SET NULL"),
    )
    for column in ("finding_id", "assessment_evidence_id", "document_version_id", "extracted_field_id"):
        op.create_index(f"ix_finding_evidence_{column}", "finding_evidence", [column])

    with op.batch_alter_table("findings") as batch_op:
        batch_op.add_column(sa.Column("requirement_assessment_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        batch_op.create_foreign_key(
            "fk_findings_requirement_assessment_id",
            "requirement_assessments",
            ["requirement_assessment_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_findings_requirement_assessment_id", ["requirement_assessment_id"])


def downgrade() -> None:
    with op.batch_alter_table("findings") as batch_op:
        batch_op.drop_index("ix_findings_requirement_assessment_id")
        batch_op.drop_constraint("fk_findings_requirement_assessment_id", type_="foreignkey")
        batch_op.drop_column("confidence")
        batch_op.drop_column("requirement_assessment_id")

    for column in ("finding_id", "assessment_evidence_id", "document_version_id", "extracted_field_id"):
        op.drop_index(f"ix_finding_evidence_{column}", table_name="finding_evidence")
    op.drop_table("finding_evidence")
    for column in ("requirement_assessment_id", "mapping_id", "document_version_id", "extracted_field_id"):
        op.drop_index(f"ix_requirement_assessment_evidence_{column}", table_name="requirement_assessment_evidence")
    op.drop_table("requirement_assessment_evidence")
    for column in ("application_id", "validation_run_id", "rule_approval_id", "applicability_status", "outcome_status", "evidence_sufficiency", "review_status"):
        op.drop_index(f"ix_requirement_assessments_{column}", table_name="requirement_assessments")
    op.drop_table("requirement_assessments")
    for column in ("application_id", "rule_approval_id", "document_version_id", "extracted_field_id", "status"):
        op.drop_index(f"ix_requirement_evidence_mappings_{column}", table_name="requirement_evidence_mappings")
    op.drop_table("requirement_evidence_mappings")
