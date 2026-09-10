"""
AI-based field & table extraction stage (spec section 4.2 / 4.3).

Sends the OCR'd/native text (with page markers) to Gemini and asks for
a structured JSON object: every meaningful field as
{value, page_number, source_text}, plus a `line_items` array for
tabular/variable-length sections (invoice lines, P&L Appropriations,
Cash Flow adjustments).

The model is instructed never to invent values: missing fields must
come back as null. We do not post-hoc validate that instruction beyond
prompting - this is documented as a known limitation.
"""
import json
import re

from google import genai
from google.genai import types as genai_types

from app.core.config import Config
from app.core.logging import get_logger
from app.services.document_type_specs import DOCUMENT_TYPES
from app.utils.exceptions import ExtractionModelError

logger = get_logger(__name__)

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not Config.GEMINI_API_KEY:
            raise ExtractionModelError("Extraction model is not configured (missing API key).")
        _client = genai.Client(api_key=Config.GEMINI_API_KEY)
    return _client


_SYSTEM_PROMPT = """You are a meticulous financial document data-extraction engine.
You will be given OCR/text-extracted content from a {doc_description}
The text is prefixed with [Page N] markers showing which page each block came from.

Rules:
1. Extract EVERY meaningful field, label and value visible in the document - not just
   the minimum fields listed below. Include header info, dates, parties, currencies,
   totals, and every financial line visible, for every period/column shown.
2. The minimum fields that MUST be attempted for this document type are: {minimum_fields}
3. If a value is not present in the text, its "value" must be null. NEVER invent, guess,
   or infer a number or label that is not actually supported by the document text.
4. For every extracted field, include the page_number it came from and a short verbatim
   source_text snippet (max ~15 words) copied from the document that supports the value.
5. NUMBER FORMATTING - read carefully, this document may use either convention:
   - Indian/financial-statement style: comma is a THOUSANDS separator, parentheses mean
     NEGATIVE. Example: "(8,404.42)" means -8404.42. "2,376,887.28" means 2376887.28.
   - Some invoices use European style: comma is a DECIMAL separator. Example: "3,49" means
     3.49, not 349. Use context (does the document look European/multi-currency, are there
     values like "17,45" next to a "10%" VAT column) to decide which convention applies,
     and apply it CONSISTENTLY across the whole document.
   - Always return numbers as plain JSON numbers: no currency symbols, no thousands
     separators, no parentheses - just the correctly-signed decimal number.
6. If the document shows a variable-length list of labeled amounts that isn't one of the
   minimum fields above - an invoice's line items, a Profit & Loss "Appropriations"
   section, or a Cash Flow "adjustments" section - return those as an array of objects in
   "line_items", using whatever key names are appropriate to the row (e.g.
   description/quantity/unit_price/amount for invoices, or label/period/value for
   statement line items).
7. Return ONLY a single valid JSON object, no markdown fences, no commentary, matching
   exactly this shape:

{{
  "extracted_data": {{
    "<field_name>": {{"value": <value or null>, "page_number": <int or null>, "source_text": "<string or null>"}},
    ...
  }},
  "line_items": [ {{...}}, ... ]
}}

Dates should be ISO 8601 (YYYY-MM-DD) where the source allows it, otherwise the raw text.
"""


def extract_fields(document_type: str, ocr_result: dict) -> dict:
    spec = DOCUMENT_TYPES[document_type]
    prompt = _SYSTEM_PROMPT.format(
        doc_description=spec["description"],
        minimum_fields=", ".join(spec["minimum_fields"]),
    )

    full_text = ocr_result["full_text"]
    if not full_text.strip():
        logger.warning("No text available to extract from (empty OCR result)")
        return {"extracted_data": {}, "line_items": []}

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=Config.GEMINI_MODEL,
            contents=f"{prompt}\n\nDOCUMENT TEXT:\n{full_text}",
            config=genai_types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        raw = response.text
    except Exception as exc:
        logger.error("Gemini extraction call failed: %s", exc)
        raise ExtractionModelError("The extraction model failed to process this document.") from exc

    return _parse_model_json(raw)


def _parse_model_json(raw: str) -> dict:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # defensive fallback in case the model wraps output in fences despite instructions
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            logger.error("Model response was not valid JSON: %s", raw[:500])
            raise ExtractionModelError("The extraction model returned an unparsable response.")
        parsed = json.loads(match.group(0))

    parsed.setdefault("extracted_data", {})
    parsed.setdefault("line_items", [])
    return parsed
