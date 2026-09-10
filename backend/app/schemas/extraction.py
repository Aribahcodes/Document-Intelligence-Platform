"""
Schemas describing the structured extraction + validation result
(spec section 5.2). Extracted fields are inherently dynamic (they vary
by document type and by what's actually visible in the document), so
`extracted_data` and `line_items` are typed loosely (dict/list) rather
than as a fixed set of named fields - the *values themselves* still
follow the {value, page_number, source_text} shape enforced by the
extraction service's prompt contract.
"""
from marshmallow import Schema, fields


class ExtractedFieldSchema(Schema):
    value = fields.Raw(allow_none=True)
    page_number = fields.Integer(allow_none=True)
    source_text = fields.String(allow_none=True)
    confidence = fields.Float(allow_none=True, required=False)


class ValidationCheckSchema(Schema):
    name = fields.String()
    formula = fields.String()
    operands = fields.Dict()
    calculated_value = fields.Float(allow_none=True)
    reported_value = fields.Float(allow_none=True)
    variance = fields.Float(allow_none=True)
    status = fields.String(metadata={"description": "PASS | FAIL | NOT_APPLICABLE"})


class ValidationResultSchema(Schema):
    checks = fields.List(fields.Nested(ValidationCheckSchema))
    overall_status = fields.String()
    issues = fields.List(fields.String())


class ProcessingMetadataSchema(Schema):
    ocr_used = fields.Boolean()
    processed_at = fields.String()
    processing_time_ms = fields.Integer()


class ProcessedDocumentResponseSchema(Schema):
    document_name = fields.String()
    document_type = fields.String()
    processing_status = fields.String()
    file_validation = fields.Dict()
    extracted_data = fields.Dict()
    line_items = fields.List(fields.Dict())
    validation = fields.Nested(ValidationResultSchema)
    processing_metadata = fields.Nested(ProcessingMetadataSchema)
