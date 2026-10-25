"""Document processing service: OCR extraction, native PDF parsing, and advisory findings.

Extracts evidence from validated and scanned documents, records immutable
observations, and evaluates preliminary consistency checks without inventing
AICTE regulatory mandates.
"""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import DocumentVersion, ExtractedField, Finding, ValidationRun
from backend.app.ocr_adapter import parse_iso_date_candidate
from backend.app.ocr_pipeline import (
    RawOCREngine,
    TesseractOCRAdapter,
    extract_institution_fields,
    process_institution_document,
)

LOW_CONFIDENCE_THRESHOLD = 0.60


class DocumentProcessingService:
    """Orchestrates native and OCR field extraction and preliminary consistency checks."""

    def __init__(self, raw_ocr_engine: RawOCREngine | None = None) -> None:
        self.raw_ocr_engine = raw_ocr_engine

    def _get_ocr_engine(self) -> RawOCREngine | None:
        if self.raw_ocr_engine is not None:
            return self.raw_ocr_engine
        try:
            return TesseractOCRAdapter()
        except Exception:
            return None

    def process_document_version(
        self,
        db: Session,
        version: DocumentVersion,
        file_bytes: bytes,
        expected_institution_id: str | None = None,
        expected_institution_name: str | None = None,
    ) -> list[ExtractedField]:
        """Extract fields from validated bytes and run preliminary consistency checks."""
        extracted_fields: list[ExtractedField] = []
        warnings: list[str] = []
        engine_name = "unknown"
        engine_version: str | None = None

        if version.media_type == "application/pdf":
            engine_name = "pdfplumber_native"
            fields_by_name = self._extract_pdf_fields(file_bytes, warnings)
        else:
            engine = self._get_ocr_engine()
            if engine is not None:
                try:
                    ocr_res = process_institution_document(file_bytes, engine)
                    engine_name = ocr_res.engine
                    engine_version = ocr_res.engine_version
                    fields_by_name = {
                        name: (
                            field.value,
                            field.confidence,
                            field.page_number,
                            field.evidence_text,
                        )
                        for name, field in ocr_res.fields.items()
                    }
                    warnings.extend(ocr_res.warnings)
                except Exception as exc:
                    warnings.append(f"Image OCR failed: {exc}")
                    fields_by_name = {}
            else:
                warnings.append("OCR system engine is not installed on host; text extraction skipped.")
                fields_by_name = {}

        # Persist extracted fields
        for field_name, (val, conf, page, evidence) in fields_by_name.items():
            if val is None:
                continue
            ef = ExtractedField(
                document_version_id=version.id,
                field_name=field_name,
                raw_text=val,
                normalized_value=val,
                confidence=conf,
                page_number=page,
                bounding_box=None,
                engine_name=engine_name,
                engine_version=engine_version,
                extraction_status="extracted",
            )
            db.add(ef)
            extracted_fields.append(ef)

        # Update version status
        version.processing_status = "succeeded" if extracted_fields else ("partial" if warnings else "succeeded")
        db.flush()

        # Run preliminary consistency checks (advisory only)
        self._evaluate_preliminary_consistency(
            db,
            version=version,
            extracted_fields=extracted_fields,
            expected_institution_id=expected_institution_id,
            expected_institution_name=expected_institution_name,
        )

        db.commit()
        for ef in extracted_fields:
            db.refresh(ef)
        return extracted_fields

    def _extract_pdf_fields(
        self,
        file_bytes: bytes,
        warnings: list[str],
    ) -> dict[str, tuple[str | None, float | None, int | None, str | None]]:
        """Extract text lines and institutional fields from PDF pages using pdfplumber."""
        fields_by_name: dict[str, tuple[str | None, float | None, int | None, str | None]] = {}
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page_idx, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    for line in text.splitlines():
                        line_clean = line.strip()
                        if not line_clean:
                            continue
                        extracted = extract_institution_fields(
                            line_clean,
                            confidence=1.0,
                            page_number=page_idx,
                        )
                        for name, ocr_field in extracted.items():
                            if name not in fields_by_name and ocr_field.value is not None:
                                fields_by_name[name] = (
                                    ocr_field.value,
                                    ocr_field.confidence,
                                    page_idx,
                                    ocr_field.evidence_text or line_clean,
                                )
        except Exception as exc:
            warnings.append(f"PDF text extraction failed: {exc}")
        return fields_by_name

    def _evaluate_preliminary_consistency(
        self,
        db: Session,
        version: DocumentVersion,
        extracted_fields: list[ExtractedField],
        expected_institution_id: str | None,
        expected_institution_name: str | None = None,
    ) -> None:
        """Run preliminary consistency checks on extracted fields and attach advisory findings."""
        findings_to_create: list[dict[str, str]] = []
        today = datetime.now(timezone.utc).date()

        fields_dict: dict[str, ExtractedField] = {f.field_name: f for f in extracted_fields}

        # 1. Expiry check on valid_until
        if "valid_until" in fields_dict:
            vu_field = fields_dict["valid_until"]
            parsed_expiry = parse_iso_date_candidate(vu_field.normalized_value)
            if parsed_expiry and parsed_expiry < today:
                findings_to_create.append({
                    "code": "DOCUMENT_EXPIRED",
                    "severity": "error",
                    "summary": f"Document expiry date {parsed_expiry.isoformat()} is before evaluation date {today.isoformat()}.",
                    "evidence": json.dumps({
                        "field_name": "valid_until",
                        "observed": parsed_expiry.isoformat(),
                        "evaluation_date": today.isoformat(),
                        "page_number": vu_field.page_number,
                    }),
                })

        # 2. Date order check (issue_date vs valid_until)
        if "issue_date" in fields_dict and "valid_until" in fields_dict:
            issue_date = parse_iso_date_candidate(fields_dict["issue_date"].normalized_value)
            valid_until = parse_iso_date_candidate(fields_dict["valid_until"].normalized_value)
            if issue_date and valid_until and issue_date > valid_until:
                findings_to_create.append({
                    "code": "INVALID_DATE_ORDER",
                    "severity": "error",
                    "summary": f"Issue date {issue_date.isoformat()} is after expiry date {valid_until.isoformat()}.",
                    "evidence": json.dumps({
                        "issue_date": issue_date.isoformat(),
                        "valid_until": valid_until.isoformat(),
                    }),
                })

        # 3. Institution identity consistency: compare like with like.
        # Prefer an explicit ID when present; otherwise compare the extracted
        # name only when the caller supplied the canonical display name.
        expected_id = str(expected_institution_id or "").strip()
        expected_name = str(expected_institution_name or "").strip()
        observed = None
        expected_value = None
        observed_field = None

        if fields_dict.get("institution_id") and fields_dict["institution_id"].normalized_value:
            observed_field = "institution_id"
            observed = fields_dict["institution_id"].normalized_value.strip()
            expected_value = expected_id
        elif fields_dict.get("institution_name") and fields_dict["institution_name"].normalized_value:
            observed_field = "institution_name"
            observed = fields_dict["institution_name"].normalized_value.strip()
            expected_value = expected_name or None

        if observed and expected_value:
            if observed.casefold() != expected_value.casefold():
                findings_to_create.append({
                    "code": "INSTITUTION_MISMATCH",
                    "severity": "warning",
                    "summary": (
                        f"Extracted {observed_field} '{observed}' does not match "
                        f"expected value '{expected_value}'."
                    ),
                    "evidence": json.dumps({
                        "field_name": observed_field,
                        "extracted": observed,
                        "expected": expected_value,
                    }),
                })

        # 4. Low confidence warning
        for f in extracted_fields:
            if f.confidence is not None and f.confidence < LOW_CONFIDENCE_THRESHOLD:
                findings_to_create.append({
                    "code": "LOW_CONFIDENCE_EXTRACTION",
                    "severity": "warning",
                    "summary": f"Field '{f.field_name}' extraction confidence ({f.confidence:.2f}) is below review threshold.",
                    "evidence": json.dumps({
                        "field_name": f.field_name,
                        "confidence": f.confidence,
                        "raw_text": f.raw_text,
                    }),
                })

        if not findings_to_create:
            return

        # Find or create advisory ValidationRun linked to the document's application
        app_id = version.document.application_id
        run_stmt = (
            select(ValidationRun)
            .where(
                ValidationRun.application_id == app_id,
                ValidationRun.status == "succeeded",
            )
            .order_by(ValidationRun.started_at.desc())
        )
        run = db.scalar(run_stmt)
        if run is None:
            run = ValidationRun(
                application_id=app_id,
                status="succeeded",
                evaluation_date=today,
                ruleset_version="0.1.0-draft",
                triggered_by="document_processing_pipeline",
            )
            db.add(run)
            db.flush()

        for f_data in findings_to_create:
            finding = Finding(
                validation_run_id=run.id,
                document_version_id=version.id,
                code=f_data["code"],
                status="open",
                severity=f_data["severity"],
                summary=f_data["summary"],
                evidence=f_data["evidence"],
            )
            db.add(finding)
        db.flush()
