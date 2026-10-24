"""Document and document version repository for database access."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Document, DocumentVersion


class DocumentRepository:
    """Encapsulates persistence operations for documents and immutable versions."""

    @staticmethod
    def create_document(
        db: Session,
        *,
        application_id: int,
        document_type: str,
    ) -> Document:
        """Create a logical document slot for an application."""
        document = Document(
            application_id=application_id,
            document_type=document_type,
        )
        db.add(document)
        return document

    @staticmethod
    def get_document(db: Session, document_id: int) -> Document | None:
        """Retrieve a document slot by its primary key ID."""
        return db.get(Document, document_id)

    @staticmethod
    def get_document_by_type(
        db: Session,
        application_id: int,
        document_type: str,
    ) -> Document | None:
        """Find a document slot by application ID and document type."""
        stmt = (
            select(Document)
            .where(
                Document.application_id == application_id,
                Document.document_type == document_type,
            )
        )
        return db.scalar(stmt)

    @staticmethod
    def list_documents_for_application(
        db: Session,
        application_id: int,
    ) -> list[Document]:
        """List all document slots for an application."""
        stmt = (
            select(Document)
            .where(Document.application_id == application_id)
            .order_by(Document.created_at.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def add_version(
        db: Session,
        *,
        document_id: int,
        version_number: int,
        storage_key: str,
        sha256: str,
        media_type: str,
        byte_size: int,
        page_count: int | None = None,
        file_name: str | None = None,
        scan_status: str | None = "pending_scan",
        processing_status: str = "queued",
    ) -> DocumentVersion:
        """Add a new immutable DocumentVersion record."""
        version = DocumentVersion(
            document_id=document_id,
            version_number=version_number,
            storage_key=storage_key,
            sha256=sha256,
            media_type=media_type,
            byte_size=byte_size,
            page_count=page_count,
            file_name=file_name,
            scan_status=scan_status,
            processing_status=processing_status,
        )
        db.add(version)
        return version

    @staticmethod
    def set_current_version(
        db: Session,
        document: Document,
        version: DocumentVersion,
    ) -> Document:
        """Update document.current_version_id pointing to the active version."""
        document.current_version_id = version.id
        return document

    @staticmethod
    def get_version(db: Session, version_id: int) -> DocumentVersion | None:
        """Retrieve an immutable document version by ID."""
        return db.get(DocumentVersion, version_id)

    @staticmethod
    def list_versions(
        db: Session,
        document_id: int,
    ) -> list[DocumentVersion]:
        """List all immutable versions for a document ordered by version number."""
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.asc())
        )
        return list(db.scalars(stmt).all())
