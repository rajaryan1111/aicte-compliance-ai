"""Tests for Authorized Institutional Record Comparison Service."""

from __future__ import annotations

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import Application, Institution, InstitutionalRecordSnapshot
from backend.app.services.institutional_record_service import InstitutionalRecordService


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


def test_institutional_records_clean_eoa_consistent(db_session: Session):
    inst = Institution(institution_id="INST-HIST-01", display_name="National Engineering Institute")
    db_session.add(inst)
    db_session.flush()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app)
    db_session.commit()

    report = InstitutionalRecordService.compare_application_against_records(db_session, app.id)
    assert report.application_id == app.id
    assert report.overall_consistency == "consistent"
    assert len(report.comparisons) == 4
    for c in report.comparisons:
        assert c.matched is True


def test_institutional_records_previous_approval_revoked(db_session: Session):
    inst = Institution(institution_id="INST-HIST-02", display_name="Deficient Institute")
    db_session.add(inst)
    db_session.flush()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app)
    db_session.flush()

    # Seed snapshot with previous status 'rejected_by_shc'
    InstitutionalRecordService.get_or_create_snapshot(
        db_session,
        inst.id,
        "previous_eoa",
        record_data={"previous_approval_status": "rejected_by_shc"},
    )
    db_session.commit()

    report = InstitutionalRecordService.compare_application_against_records(db_session, app.id)
    assert report.overall_consistency == "discrepancies_detected"
    eoa_item = next(c for c in report.comparisons if c.record_type == "previous_eoa")
    assert eoa_item.matched is False
    assert "rejected_by_shc" in eoa_item.discrepancy_explanation


def test_institutional_records_intake_change_without_nba(db_session: Session):
    inst = Institution(institution_id="INST-HIST-03", display_name="Growing Institute")
    db_session.add(inst)
    db_session.flush()

    app = Application(institution_id=inst.id, application_type="intake_change", academic_year="2026-2027")
    db_session.add(app)
    db_session.flush()

    # Institutional record has no NBA
    InstitutionalRecordService.get_or_create_snapshot(
        db_session,
        inst.id,
        "accreditation_nba",
        record_data={"has_nba_accredited_programs": False, "accredited_courses_count": 0},
    )
    db_session.commit()

    report = InstitutionalRecordService.compare_application_against_records(db_session, app.id)
    assert report.overall_consistency == "discrepancies_detected"
    nba_item = next(c for c in report.comparisons if c.record_type == "accreditation_nba")
    assert nba_item.matched is False
    assert "Clause 4.2" in nba_item.discrepancy_explanation


def test_institutional_records_ter_fee_unpaid(db_session: Session):
    inst = Institution(institution_id="INST-HIST-04", display_name="Late Fee Institute")
    db_session.add(inst)
    db_session.flush()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app)
    db_session.flush()

    InstitutionalRecordService.get_or_create_snapshot(
        db_session,
        inst.id,
        "ter_fee_payment",
        record_data={"payment_status": "failed_or_unpaid"},
    )
    db_session.commit()

    report = InstitutionalRecordService.compare_application_against_records(db_session, app.id)
    assert report.overall_consistency == "discrepancies_detected"
    ter_item = next(c for c in report.comparisons if c.record_type == "ter_fee_payment")
    assert ter_item.matched is False
    assert "failed_or_unpaid" in ter_item.discrepancy_explanation


def test_institutional_records_not_found(db_session: Session):
    with pytest.raises(ValueError, match="Application 88888 not found"):
        InstitutionalRecordService.compare_application_against_records(db_session, 88888)
