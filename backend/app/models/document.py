"""
Persistence model for a processed document.

Design note: we store the full structured result (extracted_data,
validation, file_validation, processing_metadata) as a single JSON
blob alongside a handful of indexed columns used for the dashboard
list/query. This keeps the schema simple and matches the "processed
result" concept from the spec directly - one row per processing run,
looked up by document_name for the "latest result" GET endpoint.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text, JSON

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProcessedDocument(Base):
    __tablename__ = "processed_documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    document_name = Column(String(512), nullable=False, index=True)
    document_type = Column(String(64), nullable=False)
    processing_status = Column(String(16), nullable=False)  # PASS | FAILED
    result_json = Column(JSON, nullable=False)  # full structured response (spec section 5.2)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, index=True)

    def to_summary_dict(self) -> dict:
        """Lightweight representation for the dashboard list endpoint."""
        return {
            "id": self.id,
            "document_name": self.document_name,
            "document_type": self.document_type,
            "processing_status": self.processing_status,
            "processed_at": self.created_at.isoformat() if self.created_at else None,
        }
