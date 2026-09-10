"""
Custom exceptions. Each carries an error `code` (matches the spec's
error response shape) and an HTTP `status_code`, so the API layer can
translate any of these into a consistent JSON error response without
leaking stack traces.
"""


class AppError(Exception):
    """Base class for all handled application errors."""
    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class UnsupportedFileTypeError(AppError):
    code = "UNSUPPORTED_FILE_TYPE"
    status_code = 400


class EmptyOrCorruptedFileError(AppError):
    code = "EMPTY_OR_CORRUPTED_FILE"
    status_code = 400


class PageLimitExceededError(AppError):
    code = "PAGE_LIMIT_EXCEEDED"
    status_code = 400


class InvalidDocumentTypeError(AppError):
    code = "INVALID_DOCUMENT_TYPE"
    status_code = 400


class MissingFileError(AppError):
    code = "MISSING_FILE"
    status_code = 400


class DocumentNotFoundError(AppError):
    code = "DOCUMENT_NOT_FOUND"
    status_code = 404


class OcrFailedError(AppError):
    code = "OCR_FAILED"
    status_code = 502


class ExtractionModelError(AppError):
    code = "EXTRACTION_MODEL_ERROR"
    status_code = 502


class StorageError(AppError):
    code = "STORAGE_ERROR"
    status_code = 500
