"""
Marshmallow schemas describing the document-level shapes used across
the API. Used for OpenAPI documentation and light response shaping;
the actual field extraction shape (which is dynamic per document type)
lives in schemas/extraction.py.
"""
from marshmallow import Schema, fields


class FileValidationSchema(Schema):
    file_type = fields.String(metadata={"description": "Detected MIME type, e.g. application/pdf"})
    is_supported = fields.Boolean()
    is_readable = fields.Boolean()
    page_count = fields.Integer()
    status = fields.String(metadata={"description": "PASS or FAILED"})


class DocumentSummarySchema(Schema):
    """Row shape used by GET /api/v1/documents (dashboard list)."""
    id = fields.String()
    document_name = fields.String()
    document_type = fields.String()
    processing_status = fields.String()
    processed_at = fields.String()


class DocumentListResponseSchema(Schema):
    documents = fields.List(fields.Nested(DocumentSummarySchema))


class ProcessDocumentRequestSchema(Schema):
    """Documents the multipart/form-data fields expected by POST /documents/process."""
    document_type = fields.String(
        required=True,
        metadata={"description": "One of: invoice, balance_sheet, profit_and_loss, cash_flow_statement"},
    )


class ErrorDetailSchema(Schema):
    code = fields.String()
    message = fields.String()


class ErrorResponseSchema(Schema):
    error = fields.Nested(ErrorDetailSchema)
