"""
Orchestrates the full processing pipeline (spec section 1 diagram):

  validate file -> OCR/text extraction -> AI field extraction ->
  financial validation -> determine PASS/FAILED -> persist -> return JSON

This is the only place that calls multiple services in sequence, so
that each individual service stays narrowly responsible and testable.
"""
import time
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.repositories.document_repository import DocumentRepository
from app.services import (
    document_validation_service,
    ocr_service,
    extraction_service,
    financial_validation_service,
)
from app.services.document_type_specs import is_valid_document_type
from app.utils.exceptions import AppError, InvalidDocumentTypeError, MissingFileError

logger = get_logger(__name__)
_repo = DocumentRepository()


def process_document(filename: str, file_bytes: bytes, document_type: str) -> dict:
    started = time.monotonic()

    if not filename:
        raise MissingFileError("A file must be provided.")
    if not is_valid_document_type(document_type):
        raise InvalidDocumentTypeError(
            "document_type must be one of: invoice, balance_sheet, profit_and_loss, cash_flow_statement."
        )

    logger.info("Processing document '%s' as %s", filename, document_type)

    try:
        file_validation = document_validation_service.validate_file(filename, file_bytes)
    except AppError as exc:
        # file validation failure -> FAILED result, still persisted so it shows on the dashboard
        result = _build_failed_result(filename, document_type, str(exc), started, file_validation=None)
        _persist(filename, document_type, "FAILED", result)
        raise

    ocr_result = ocr_service.extract_pages(file_bytes, file_validation["file_type"])
    extraction = extraction_service.extract_fields(document_type, ocr_result)
    extracted_data = extraction.get("extracted_data", {})
    line_items = extraction.get("line_items", [])

    validation = financial_validation_service.validate(document_type, extracted_data, line_items)

    # Per spec 4.5: PASS = fields extracted and required validations pass. A validation FAIL
    # is a finding about the document, not a processing failure - the document WAS processed
    # successfully, so processing_status stays PASS with the failed checks surfaced clearly in
    # `validation`. FAILED is reserved for documents that could not be processed at all (file
    # validation failure above, or zero fields extracted below).
    processing_status = "PASS" if extracted_data else "FAILED"

    elapsed_ms = int((time.monotonic() - started) * 1000)

    result = {
        "document_name": filename,
        "document_type": document_type,
        "processing_status": processing_status,
        "file_validation": file_validation,
        "extracted_data": extracted_data,
        "line_items": line_items,
        "validation": validation,
        "processing_metadata": {
            "ocr_used": ocr_result["ocr_used"],
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "processing_time_ms": elapsed_ms,
        },
    }

    _persist(filename, document_type, processing_status, result)
    logger.info("Finished processing '%s' -> status=%s in %dms", filename, processing_status, elapsed_ms)
    return result


def _build_failed_result(filename, document_type, error_message, started, file_validation) -> dict:
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "document_name": filename,
        "document_type": document_type,
        "processing_status": "FAILED",
        "file_validation": file_validation,
        "extracted_data": {},
        "line_items": [],
        "validation": {"checks": [], "overall_status": "NOT_APPLICABLE", "issues": [error_message]},
        "processing_metadata": {
            "ocr_used": False,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "processing_time_ms": elapsed_ms,
        },
    }


def _persist(filename: str, document_type: str, status: str, result: dict) -> None:
    _repo.save(document_name=filename, document_type=document_type,
               processing_status=status, result_json=result)


def get_by_name(document_name: str) -> dict:
    record = _repo.get_latest_by_name(document_name)
    return record.result_json if record else None


def list_documents() -> list:
    records = _repo.list_all()
    return [r.to_summary_dict() for r in records]
