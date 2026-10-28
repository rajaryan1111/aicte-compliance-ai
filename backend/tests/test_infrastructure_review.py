"""Tests for Infrastructure Compliance Review Service and EVC physical inspection triggers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import Application, Document, DocumentVersion, ExtractedField, Institution
from backend.app.services.infrastructure_review_service import InfrastructureReviewService


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_infrastructure_review_compliant(db_session: Session):
    inst = Institution(institution_id="INST-INFRA-01", display_name="Campus Alpha")
    db_session.add(inst)
    db_session.flush()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app)
    db_session.flush()

    # Structural stability with future expiry
    doc_struct = Document(application_id=app.id, document_type="structural_stability")
    db_session.add(doc_struct)
    db_session.flush()

    ver_struct = DocumentVersion(
        document_id=doc_struct.id,
        version_number=1,
        storage_key="struct.pdf",
        sha256="abc111" + "0" * 58,
        media_type="application/pdf",
        byte_size=200_000,
        scan_status="clean",
    )
    db_session.add(ver_struct)
    db_session.flush()
    doc_struct.current_version_id = ver_struct.id

    future_date = (datetime.now(timezone.utc).date() + timedelta(days=365)).isoformat()
    field = ExtractedField(
        document_version_id=ver_struct.id,
        field_name="valid_until",
        raw_text=future_date,
        normalized_value=future_date,
        engine_name="test",
    )
    db_session.add(field)

    # Campus photo of acceptable size
    doc_photo = Document(application_id=app.id, document_type="campus_photo")
    db_session.add(doc_photo)
    db_session.flush()

    ver_photo = DocumentVersion(
        document_id=doc_photo.id,
        version_number=1,
        storage_key="photo.jpg",
        sha256="abc222" + "0" * 58,
        media_type="image/jpeg",
        byte_size=150_000,
        scan_status="clean",
    )
    db_session.add(ver_photo)
    db_session.flush()
    doc_photo.current_version_id = ver_photo.id
    db_session.commit()

    summary = InfrastructureReviewService.review_application_infrastructure(
        db_session, app.id, actor_id="officer_infra"
    )

    assert summary.overall_status == "preliminary_compliant"
    assert summary.physical_inspection_recommended is False
    assert len(summary.inspection_reasons) == 0
    assert len(summary.items) == 2


def test_infrastructure_review_low_res_photo_triggers_evc(db_session: Session):
    inst = Institution(institution_id="INST-INFRA-02", display_name="Campus Beta")
    db_session.add(inst)
    db_session.flush()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app)
    db_session.flush()

    doc_photo = Document(application_id=app.id, document_type="laboratory_photo")
    db_session.add(doc_photo)
    db_session.flush()

    # Small photo (< 50,000 bytes)
    ver_photo = DocumentVersion(
        document_id=doc_photo.id,
        version_number=1,
        storage_key="low_res.jpg",
        sha256="abc333" + "0" * 58,
        media_type="image/jpeg",
        byte_size=12_000,
        scan_status="clean",
    )
    db_session.add(ver_photo)
    db_session.flush()
    doc_photo.current_version_id = ver_photo.id
    db_session.commit()

    summary = InfrastructureReviewService.review_application_infrastructure(
        db_session, app.id, actor_id="officer_infra"
    )

    assert summary.overall_status == "inspection_recommended"
    assert summary.physical_inspection_recommended is True
    assert any("resolution is unusually low" in r for r in summary.inspection_reasons)


def test_infrastructure_review_expired_structural_triggers_evc(db_session: Session):
    inst = Institution(institution_id="INST-INFRA-03", display_name="Campus Gamma")
    db_session.add(inst)
    db_session.flush()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app)
    db_session.flush()

    doc_struct = Document(application_id=app.id, document_type="structural_stability")
    db_session.add(doc_struct)
    db_session.flush()

    ver_struct = DocumentVersion(
        document_id=doc_struct.id,
        version_number=1,
        storage_key="expired_struct.pdf",
        sha256="abc444" + "0" * 58,
        media_type="application/pdf",
        byte_size=100_000,
        scan_status="clean",
    )
    db_session.add(ver_struct)
    db_session.flush()
    doc_struct.current_version_id = ver_struct.id

    # Past expiry date
    past_date = "2023-01-01"
    field = ExtractedField(
        document_version_id=ver_struct.id,
        field_name="valid_until",
        raw_text=past_date,
        normalized_value=past_date,
        engine_name="test",
    )
    db_session.add(field)
    db_session.commit()

    summary = InfrastructureReviewService.review_application_infrastructure(
        db_session, app.id, actor_id="officer_infra"
    )

    assert summary.overall_status == "inspection_recommended"
    assert summary.physical_inspection_recommended is True
    assert any("expired" in r.lower() for r in summary.inspection_reasons)

    # Check persistence in db
    evidence_list = InfrastructureReviewService.list_evidence(db_session, app.id)
    assert len(evidence_list) == 1
    assert evidence_list[0].inspection_recommended is True


def test_infrastructure_review_missing_application(db_session: Session):
    with pytest.raises(ValueError, match="Application 99999 not found"):
        InfrastructureReviewService.review_application_infrastructure(
            db_session, application_id=99999
        )
