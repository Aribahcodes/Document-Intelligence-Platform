"""
Data-access layer for processed documents. All DB queries live here -
services should never import SQLAlchemy directly.
"""
from app.core.database import get_session
from app.models.document import ProcessedDocument


class DocumentRepository:
    def save(self, document_name: str, document_type: str, processing_status: str,
              result_json: dict, error_message: str | None = None) -> ProcessedDocument:
        session = get_session()
        try:
            record = ProcessedDocument(
                document_name=document_name,
                document_type=document_type,
                processing_status=processing_status,
                result_json=result_json,
                error_message=error_message,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record
        finally:
            session.close()

    def get_latest_by_name(self, document_name: str) -> ProcessedDocument | None:
        session = get_session()
        try:
            return (
                session.query(ProcessedDocument)
                .filter(ProcessedDocument.document_name == document_name)
                .order_by(ProcessedDocument.created_at.desc())
                .first()
            )
        finally:
            session.close()

    def list_all(self, limit: int = 200) -> list[ProcessedDocument]:
        session = get_session()
        try:
            return (
                session.query(ProcessedDocument)
                .order_by(ProcessedDocument.created_at.desc())
                .limit(limit)
                .all()
            )
        finally:
            session.close()
