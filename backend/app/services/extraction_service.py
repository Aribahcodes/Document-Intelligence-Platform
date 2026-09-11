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

Transient server-side failures (503 UNAVAILABLE - "high demand", or
429 rate limiting) are retried automatically with a short backoff,
since these are genuinely temporary and a retry a couple of seconds
later routinely succeeds (confirmed against real traffic while testing
this project - roughly 1 in 4 calls hit a transient 503 under normal
free-tier load). Non-retryable errors (bad API key, invalid request,
etc.) raise ClientError instead of ServerError and are not retried -
retrying those would just waste time on something that will never
succeed.
"""
import json
import re
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.core.config import Config
from app.core.logging import get_logger
from app.services.document_type_specs import DOCUMENT_TYPES
from app.utils.exceptions import ExtractionModelError

logger = get_logger(__name__)

_client = None

# retry only server-side/transient status codes - never retry 4xx client
# errors (bad key, malformed request, etc.), since those will never
# succeed no matter how many times we ask
_RETRYABLE_CODES = {429, 500, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = 2  # doubles each retry: 2s, 4s


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
   or infer a number or label that is not actually supported by the document text. HOWEVER,
   if a field's row IS present but shows a dash/hyphen ("-") instead of a number - a common
   convention in financial statements for a nil/zero amount - extract that as the number 0,
   NOT as null. Null means "this field does not appear in the document at all"; 0 means "this
   field appears and is explicitly zero."
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

    raw = _call_gemini_with_retry(prompt, full_text)
    return _parse_model_json(raw)


def _call_gemini_with_retry(prompt: str, full_text: str) -> str:
    client = _get_client()
    last_exc = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=Config.GEMINI_MODEL,
                contents=f"{prompt}\n\nDOCUMENT TEXT:\n{full_text}",
                config=genai_types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            return response.text

        except genai_errors.ServerError as exc:
            last_exc = exc
            if exc.code not in _RETRYABLE_CODES or attempt == _MAX_ATTEMPTS:
                logger.error("Gemini extraction call failed (attempt %d/%d, non-retryable or exhausted): %s",
                             attempt, _MAX_ATTEMPTS, exc)
                break
            wait = _BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.warning("Gemini returned a transient error (code=%s, attempt %d/%d) - retrying in %ds: %s",
                            exc.code, attempt, _MAX_ATTEMPTS, wait, exc)
            time.sleep(wait)

        except Exception as exc:
            # non-ServerError failures (bad key, network issue, malformed
            # request, etc.) are never retried - they won't succeed on a
            # second attempt
            last_exc = exc
            logger.error("Gemini extraction call failed (non-retryable): %s", exc)
            break

    raise ExtractionModelError("The extraction model failed to process this document.") from last_exc


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
