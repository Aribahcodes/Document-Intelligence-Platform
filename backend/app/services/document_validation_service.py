"""
Input-control layer (spec section 4.1). Validates file type, basic
integrity and page count BEFORE any OCR/extraction is attempted. This
is deliberately dumb about document *content* - it only checks that
the upload is a readable PDF/JPG/PNG within the page limit.
"""
import fitz  # PyMuPDF
from PIL import Image

from app.core.config import Config
from app.core.logging import get_logger
from app.utils.exceptions import (
    EmptyOrCorruptedFileError,
    PageLimitExceededError,
    UnsupportedFileTypeError,
)

logger = get_logger(__name__)

_EXT_TO_MIME = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


def _guess_mime_type(filename: str, file_bytes: bytes) -> str:
    # sniff by magic bytes first (more reliable than trusting the extension)
    if file_bytes[:4] == b"%PDF":
        return "application/pdf"
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if file_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    # fall back to extension
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _EXT_TO_MIME.get(ext, "application/octet-stream")


def validate_file(filename: str, file_bytes: bytes) -> dict:
    """
    Returns the file_validation dict from spec section 4.1 on success.
    Raises AppError subclasses on failure - callers turn these into
    the FAILED processing_status + error response.
    """
    if not file_bytes or len(file_bytes) == 0:
        logger.warning("Rejected empty upload: %s", filename)
        raise EmptyOrCorruptedFileError("The uploaded file is empty.")

    if len(file_bytes) > Config.MAX_UPLOAD_SIZE_BYTES:
        logger.warning("Rejected oversized upload: %s (%d bytes)", filename, len(file_bytes))
        raise EmptyOrCorruptedFileError("The uploaded file exceeds the maximum allowed size.")

    mime_type = _guess_mime_type(filename, file_bytes)
    if mime_type not in Config.ALLOWED_MIME_TYPES:
        logger.warning("Rejected unsupported file type: %s (%s)", filename, mime_type)
        raise UnsupportedFileTypeError("Only PDF / JPG / PNG documents are supported.")

    page_count = 1
    if mime_type == "application/pdf":
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page_count = doc.page_count
            if page_count == 0:
                raise EmptyOrCorruptedFileError("The PDF contains no pages.")
            # touch the first page to confirm the file is actually readable
            _ = doc[0].get_text()
            doc.close()
        except EmptyOrCorruptedFileError:
            raise
        except Exception as exc:
            logger.warning("Rejected corrupted PDF: %s (%s)", filename, exc)
            raise EmptyOrCorruptedFileError("The PDF could not be read; it may be corrupted.") from exc
    else:
        try:
            from io import BytesIO
            img = Image.open(BytesIO(file_bytes))
            img.verify()
        except Exception as exc:
            logger.warning("Rejected corrupted image: %s (%s)", filename, exc)
            raise EmptyOrCorruptedFileError("The image could not be read; it may be corrupted.") from exc

    if page_count > Config.MAX_PAGE_COUNT:
        logger.warning("Rejected document exceeding page limit: %s (%d pages)", filename, page_count)
        raise PageLimitExceededError(
            f"Document has {page_count} pages; the maximum supported is {Config.MAX_PAGE_COUNT}."
        )

    logger.info("File validated OK: %s (%s, %d page(s))", filename, mime_type, page_count)
    return {
        "file_type": mime_type,
        "is_supported": True,
        "is_readable": True,
        "page_count": page_count,
        "status": "PASS",
    }
