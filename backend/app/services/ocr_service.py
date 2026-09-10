"""
Text extraction / OCR stage (spec section 4.1 -> pipeline step
"Text Extraction / OCR").

Strategy:
  - Native PDFs: extract the text layer directly with PyMuPDF. This is
    fast and has no OCR error rate.
  - Scanned PDFs (pages with little/no text layer) and standalone
    JPG/PNG uploads: rasterize the page and run Tesseract OCR.

Each page is judged independently, so a PDF that mixes native and
scanned pages is handled page-by-page. Returns per-page text plus an
overall `ocr_used` flag for processing_metadata.
"""
from io import BytesIO

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from app.core.config import Config
from app.core.logging import get_logger
from app.utils.exceptions import OcrFailedError

logger = get_logger(__name__)

if Config.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_CMD

RASTER_DPI = 200


def extract_pages(file_bytes: bytes, mime_type: str) -> dict:
    """
    Returns:
      {
        "pages": [{"page_number": 1, "text": "...", "ocr_used": false}, ...],
        "ocr_used": bool,  # true if ANY page required OCR
        "full_text": "concatenated text across all pages"
      }
    """
    try:
        if mime_type == "application/pdf":
            return _extract_pdf(file_bytes)
        return _extract_image(file_bytes)
    except OcrFailedError:
        raise
    except Exception as exc:
        logger.error("Text extraction failed: %s", exc)
        raise OcrFailedError("Unable to extract text from the document.") from exc


def _extract_pdf(file_bytes: bytes) -> dict:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    any_ocr = False

    for i in range(doc.page_count):
        page = doc[i]
        native_text = page.get_text().strip()

        if len(native_text) >= Config.OCR_TEXT_MIN_CHARS:
            pages.append({"page_number": i + 1, "text": native_text, "ocr_used": False})
            continue

        # sparse/no text layer -> treat as scanned, rasterize and OCR
        any_ocr = True
        pix = page.get_pixmap(dpi=RASTER_DPI)
        img = Image.open(BytesIO(pix.tobytes("png")))
        ocr_text = pytesseract.image_to_string(img).strip()
        pages.append({"page_number": i + 1, "text": ocr_text, "ocr_used": True})
        logger.info("Page %d had no reliable text layer; used Tesseract OCR", i + 1)

    doc.close()
    full_text = "\n\n".join(f"[Page {p['page_number']}]\n{p['text']}" for p in pages)
    return {"pages": pages, "ocr_used": any_ocr, "full_text": full_text}


def _extract_image(file_bytes: bytes) -> dict:
    img = Image.open(BytesIO(file_bytes))
    text = pytesseract.image_to_string(img).strip()
    pages = [{"page_number": 1, "text": text, "ocr_used": True}]
    full_text = f"[Page 1]\n{text}"
    return {"pages": pages, "ocr_used": True, "full_text": full_text}
