"""Tests for OCR/native document processing service, extracted evidence, and advisory findings."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import Application, Document, DocumentVersion, Finding, Institution
from backend.app.ocr_pipeline import OCRRawResult, OCRWord
from backend.app.services.document_processing_service import DocumentProcessingService

VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\n\x00\x00\x00\n\x08\x02\x00\x00\x00\x02PX\xea"
    b"\x00\x00\x00\x16IDATx\x9cc\xfc\xff\xff?\x03n\xc0\x84G\x8ea\xe4J\x03\x00\xa5\xe3\x03\x11\xc7z\x1cU"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def db_session():
    """Isolated in-memory database session."""
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


def create_synthetic_pdf_bytes(lines: list[str]) -> bytes:
    """Helper to build a valid synthetic PDF with clean line-separated text."""
    parts = ["BT /F1 12 Tf 50 700 Td"]
    for i, line in enumerate(lines):
        if i == 0:
            parts.append(f"({line}) Tj")
        else:
            parts.append(f"0 -20 Td ({line}) Tj")
    parts.append("ET")
    stream_data = " ".join(parts).encode("utf-8")
    stream_len = len(stream_data)

    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(stream_len).encode("utf-8") + b" >>\nstream\n"
        + stream_data + b"\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000240 00000 n \n0000000350 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n450\n%%EOF"
    )
    return pdf


class MockRawEngine:
    """Synthetic test double for raw OCR engine."""

    def __init__(self, words: list[OCRWord]) -> None:
        self.words = words

    def recognize(self, image_bytes: bytes) -> OCRRawResult:
        return OCRRawResult(tuple(self.words), "mock_engine", "1.0")


def test_pdf_extraction_persists_extracted_fields(db_session: Session):
    """Verify that PDF text lines are extracted and stored against the document version."""
    inst = Institution(institution_id="INST-PROC-01", display_name="Test Inst")
    app = Application(institution=inst, application_type="eoa", academic_year="2026-2027", status="draft")
    doc = Document(application=app, document_type="eoa_approval")
    version = DocumentVersion(
        document=doc,
        version_number=1,
        storage_key="docs/01/v1.pdf",
        sha256="a" * 64,
        media_type="application/pdf",
        byte_size=1024,
        processing_status="processing",
    )
    db_session.add_all([inst, app, doc, version])
    db_session.commit()

    pdf_bytes = create_synthetic_pdf_bytes([
        "Institution Name: Test Institute",
        "Valid Until: 2029-06-30",
        "Issue Date: 2024-04-01",
        "Academic Year: 2026-2027",
    ])

    service = DocumentProcessingService()
    fields = service.process_document_version(
        db_session,
        version=version,
        file_bytes=pdf_bytes,
        expected_institution_id="Test Institute",
    )

    assert len(fields) >= 2
    field_dict = {f.field_name: f.normalized_value for f in fields}
    assert field_dict.get("institution_name") == "Test Institute"
    assert field_dict.get("valid_until") == "2029-06-30"
    assert version.processing_status == "succeeded"


def test_advisory_finding_expired_document(db_session: Session):
    """Verify advisory finding generation when valid_until is expired."""
    inst = Institution(institution_id="INST-EXP-01", display_name="Expired Inst")
    app = Application(institution=inst, application_type="eoa", academic_year="2026-2027", status="draft")
    doc = Document(application=app, document_type="land_docs")
    version = DocumentVersion(
        document=doc,
        version_number=1,
        storage_key="docs/02/v1.pdf",
        sha256="b" * 64,
        media_type="application/pdf",
        byte_size=1024,
        processing_status="processing",
    )
    db_session.add_all([inst, app, doc, version])
    db_session.commit()

    past_date = (date.today() - timedelta(days=30)).isoformat()
    pdf_bytes = create_synthetic_pdf_bytes([
        "Institution Name: Expired Inst",
        f"Valid Until: {past_date}",
    ])

    service = DocumentProcessingService()
    service.process_document_version(db_session, version=version, file_bytes=pdf_bytes)

    # Check finding
    findings = list(db_session.scalars(select(Finding).where(Finding.document_version_id == version.id)).all())
    assert any(f.code == "DOCUMENT_EXPIRED" and f.severity == "error" for f in findings)


def test_advisory_finding_institution_mismatch(db_session: Session):
    """Verify advisory finding generation when extracted institution ID/name differs from application."""
    inst = Institution(institution_id="INST-EXPECTED-99", display_name="Expected Inst")
    app = Application(institution=inst, application_type="eoa", academic_year="2026-2027", status="draft")
    doc = Document(application=app, document_type="eoa_approval")
    version = DocumentVersion(
        document=doc,
        version_number=1,
        storage_key="docs/03/v1.pdf",
        sha256="c" * 64,
        media_type="application/pdf",
        byte_size=1024,
        processing_status="processing",
    )
    db_session.add_all([inst, app, doc, version])
    db_session.commit()

    pdf_bytes = create_synthetic_pdf_bytes([
        "Institution Name: Other Unrelated Institute",
        "Valid Until: 2028-06-30",
    ])

    service = DocumentProcessingService()
    service.process_document_version(
        db_session,
        version=version,
        file_bytes=pdf_bytes,
        expected_institution_id="Expected Inst",
    )

    findings = list(db_session.scalars(select(Finding).where(Finding.document_version_id == version.id)).all())
    assert any(f.code == "INSTITUTION_MISMATCH" and f.severity == "warning" for f in findings)


def test_low_confidence_extraction_warning(db_session: Session):
    """Verify that low-confidence OCR field generates a LOW_CONFIDENCE_EXTRACTION finding."""
    inst = Institution(institution_id="INST-CONF-01", display_name="Conf Inst")
    app = Application(institution=inst, application_type="eoa", academic_year="2026-2027", status="draft")
    doc = Document(application=app, document_type="eoa_approval")
    version = DocumentVersion(
        document=doc,
        version_number=1,
        storage_key="docs/04/v1.png",
        sha256="d" * 64,
        media_type="image/png",
        byte_size=1024,
        processing_status="processing",
    )
    db_session.add_all([inst, app, doc, version])
    db_session.commit()

    # Synthetic words with low confidence (0.45) matching "institution name: Tech Institute"
    mock_words = [
        OCRWord(text="institution", confidence=0.45, line_number=1),
        OCRWord(text="name:", confidence=0.45, line_number=1),
        OCRWord(text="Tech Institute", confidence=0.45, line_number=1),
    ]
    mock_engine = MockRawEngine(mock_words)

    service = DocumentProcessingService(raw_ocr_engine=mock_engine)
    service.process_document_version(db_session, version=version, file_bytes=VALID_PNG_BYTES)

    findings = list(db_session.scalars(select(Finding).where(Finding.document_version_id == version.id)).all())
    assert any(f.code == "LOW_CONFIDENCE_EXTRACTION" for f in findings)
