# Document Intelligence Platform

An AI-powered document extraction and validation platform for financial
documents (invoices, balance sheets, profit & loss statements, cash flow
statements). Built for the AI Engineer Internship technical case study.

- **Live frontend:** https://document-intelligence-platform-qip5.onrender.com
- **Live backend API:** https://document-intelligence-platform-qip5.onrender.com/api/v1
- **Swagger / OpenAPI docs:** https://document-intelligence-platform-qip5.onrender.com/docs
- **Health check:** https://document-intelligence-platform-qip5.onrender.com/api/v1/health
- **GitHub repository:** https://github.com/Aribahcodes/Document-Intelligence-Platform

---

## 1. Solution overview

The platform accepts a PDF/JPG/PNG financial document through a web
dashboard or directly via a REST API, and runs it through a pipeline:

```
Upload
  |
File validation (PDF/JPG/PNG, integrity, page limit)
  |
Text extraction / OCR
  |
AI field extraction
  |
Financial validation
  |
Store result
  |
PASS / FAILED
  |
Dashboard + REST API
```

See [`docs/architecture.png`](docs/architecture.png) for the full component
diagram. In short: a single Flask application serves both a REST API and a
frontend page shell. **The frontend never talks to the backend's internal
services directly** - it calls the same public REST API any external
client would use, via client-side `fetch()`. This was a deliberate
architectural choice (see Section 2) so the API is a genuinely independent,
fully-functional contract, not just an implementation detail behind the
dashboard.

## 2. Technology stack and why

| Concern | Choice | Why |
|---|---|---|
| Backend framework | **Flask** + flask-smorest | Lightweight, spec explicitly allows Flask; flask-smorest gives auto-generated Swagger/OpenAPI docs (`/docs`) for free |
| Text extraction / OCR | **PyMuPDF** (native PDF text layer) + **Tesseract** (fallback for scanned pages/images) | Native-PDF text extraction is fast and has zero OCR error rate; Tesseract is free, needs no API key, and runs entirely offline. Each *page* is judged independently, so a PDF that mixes native and scanned pages is handled correctly. In practice, every financial statement in the test dataset turned out to be image-based (no text layer at all), so nearly all real testing exercised the Tesseract path. |
| Field extraction (AI) | **Gemini API** (`gemini-3.6-flash`) | Free tier, strong structured-JSON output. `GEMINI_MODEL` is a configurable env var specifically because Gemini's model lineup changes frequently - the project actually hit a real deprecation of `gemini-2.0-flash` mid-build and had to switch models, which is exactly the scenario this makes painless. |
| Database | **SQLite** via SQLAlchemy | Zero setup, file-based, meets the spec's minimum bar. `DATABASE_URL` is the only thing that needs to change to point at Postgres/MySQL instead - no other code changes required. |
| Frontend | **Bootstrap 5 (CDN) + server-rendered Jinja2 shells + vanilla JS `fetch()`** | Bootstrap gives a polished, accessible UI (forms, tables, toasts, tabs) with almost no custom CSS. The frontend calls the real deployed REST API for every piece of data (upload, list, get-by-name) rather than Flask calling its own service layer internally - this is what makes the "frontend must call the deployed backend/API" requirement genuinely true, not just technically true. |
| Deployment | **Docker on Render** (see `render.yaml` / `Dockerfile`) | Tesseract is a system package, not a pip package, so the deployment platform needs Docker support; Render's free tier supports this. |

## 3. Local setup instructions

**Prerequisites:** Python 3.10+, Tesseract OCR installed locally, a Gemini API key.

```bash
git clone https://github.com/Aribahcodes/Document-Intelligence-Platform.git
cd Document-Intelligence-Platform

cp .env.example .env
# edit .env: set GEMINI_API_KEY at minimum

cd backend
pip install -r requirements.txt
python -m app.main
# -> serves on http://localhost:8000 (dashboard at /, API under /api/v1, docs at /docs)
```

**Run with Docker instead** (matches the deployed environment exactly):

```bash
docker build -t doc-intel .
docker run -p 8000:8000 --env-file .env doc-intel
```

**Run tests:**

```bash
cd backend
pytest tests/ -v
```

All 33 tests are offline/deterministic - the Gemini call is mocked in
`test_extraction.py` and `test_api.py`, so no network access, API key, or
quota is required to run the suite.

## 4. Environment variables

See [`.env.example`](.env.example) for the full list with defaults. The
ones that matter most:

- `GEMINI_API_KEY` - required for the extraction step to actually call the
  model. Get one at https://aistudio.google.com/apikey (free tier).
- `GEMINI_MODEL` - defaults to `gemini-3.6-flash`. Kept configurable
  because Gemini model availability changes frequently - see Section 9.
- `DATABASE_URL` - defaults to a local SQLite file; set to a Postgres URL
  to use a managed database instead.

No secrets are hardcoded anywhere in the codebase - `app/core/config.py`
reads everything from the environment, `.env` is git-ignored, and on
Render the real `GEMINI_API_KEY` is set directly in the platform's
dashboard (`render.yaml` marks it `sync: false` specifically so it's never
committed).

## 5. API reference

Full interactive documentation is live at
https://document-intelligence-platform-qip5.onrender.com/docs. Summary:

### `POST /api/v1/documents/process`

```bash
curl -X POST https://document-intelligence-platform-qip5.onrender.com/api/v1/documents/process \
  -F "file=@sample_invoice.pdf" \
  -F "document_type=invoice"
```

Returns the full structured result described in spec section 5.2
(`document_name`, `document_type`, `processing_status`, `file_validation`,
`extracted_data`, `line_items`, `validation`, `processing_metadata`). See
[`sample_outputs/`](sample_outputs/) for real examples covering all 4
document types, a validation-failure case, a missing-fields case, and
error cases.

### `GET /api/v1/documents/{document_name}`

```bash
curl https://document-intelligence-platform-qip5.onrender.com/api/v1/documents/sample_invoice.pdf
```

Returns the **latest** stored result for that document name (404 with a
structured error if never processed). If the same name is processed more
than once, this returns the most recent result (spec section 5.1).

### `GET /api/v1/documents`

```bash
curl https://document-intelligence-platform-qip5.onrender.com/api/v1/documents
```

Returns a summary list (`document_name`, `document_type`,
`processing_status`, `processed_at`) - this is exactly what the
dashboard's History tab fetches client-side.

### `GET /api/v1/health`

```bash
curl https://document-intelligence-platform-qip5.onrender.com/api/v1/health
```

`{"status": "ok"}` - the mandatory health check, wired directly into
Render's own platform health monitoring via `render.yaml`.

### Error shape

Every failure - expected (bad upload) or unexpected - returns:

```json
{"error": {"code": "UNSUPPORTED_FILE_TYPE", "message": "Only PDF / JPG / PNG documents are supported."}}
```

Stack traces are never exposed to the client; unexpected exceptions are
logged server-side and returned as a generic `INTERNAL_ERROR` (500).

## 6. OCR / extraction approach in detail

1. **File validation** (`document_validation_service`) - sniffs the real
   MIME type from file magic bytes (not just the extension), rejects
   anything outside PDF/JPG/PNG, rejects empty/corrupted files, and
   rejects documents over 3 pages.
2. **Text extraction** (`ocr_service`) - for PDFs, each page's native text
   layer is extracted with PyMuPDF. If a page yields fewer than
   `OCR_TEXT_MIN_CHARS` (default 30) characters, it's treated as scanned:
   the page is rasterized at 200 DPI and run through Tesseract. Standalone
   JPG/PNG uploads always go through Tesseract.
3. **Field extraction** (`extraction_service`) - the page-tagged text is
   sent to Gemini with a prompt that (a) lists the minimum required fields
   for the given `document_type`, (b) instructs the model to extract
   *every* meaningful visible field/line item, not just the minimum list,
   (c) forbids inventing values - missing fields must come back as
   `null` - but treats a dash/hyphen in a financial statement row as an
   explicit `0`, not a missing value, (d) gives explicit rules for two
   different number formatting conventions found in the real test data
   (Indian-statement comma-as-thousands-separator vs. European
   comma-as-decimal-separator), and (e) requires a `source_text` +
   `page_number` for every extracted value (evidence/grounding, spec
   4.3). The model is called with `temperature=0.0` and
   `response_mime_type: application/json`.
4. **Retry logic** - transient failures (503 "high demand", 429 rate
   limiting) are retried up to 3 times with exponential backoff (2s, 4s).
   This was added after live testing showed roughly 1 in 4 real calls
   hitting a transient 503 under normal free-tier load. Non-retryable
   errors (bad API key, malformed request) fail immediately rather than
   wasting time retrying something that can never succeed.
5. **Financial validation** (`financial_validation_service`) - see Section 7.
6. **Persistence** - the full result is stored as a JSON blob in SQLite,
   one row per processing run, keyed by document name + timestamp.

**Confidence scoring is intentionally omitted.** The spec marks it
optional and explicitly says values should be "meaningful and
explainable rather than arbitrary LLM-generated values" - without a
real confidence signal (e.g. logprobs, or a second cross-check pass) an
LLM-reported confidence number is just a plausible-looking guess.
`source_text` + `page_number` evidence is provided for every field
instead, which the spec calls "strongly preferred" anyway.

## 7. Financial validation rules and tolerance

Every check returns `{name, formula, operands, calculated_value,
reported_value, variance, status}`, where `status` is `PASS`, `FAIL`, or
`NOT_APPLICABLE` (never invented when a required input is missing).
Tolerance is **1% relative (or 0.01 absolute, whichever is larger)**,
configurable via `VALIDATION_TOLERANCE`.

**Invoice:** `subtotal + tax_amount - discount ~= total_amount`; sum of
line items reconciled to subtotal; per-line `quantity * unit_price ~=
amount`; `cash_paid - total_amount ~= change` when present.

**Balance sheet, Profit & Loss, Cash Flow statement:** these three
document types in the real test dataset are genuine bank-format
consolidated financial statements (HDFC Bank annual reports, 2017-2024),
each showing **two comparative periods side by side**. Every check
therefore runs twice - once per period - with the `current_`/`prior_`
prefix on every field name. If a document only shows one period, the
missing period's checks correctly report `NOT_APPLICABLE`, not `FAIL`.

- **Balance sheet:** `total_capital_and_liabilities ~= total_assets`,
  plus independent reconciliation of each side's own components
  (Capital, Reserves, Deposits, Borrowings... vs. Cash, Investments,
  Advances...).
- **Profit & Loss:** `interest_earned + other_income ~= total_income`;
  `interest_expended + operating_expenses + provisions ~=
  total_expenditure`; `total_income - total_expenditure ~=
  net_profit_before_minority_interest`; `net_profit_before_minority -
  minority_interest ~= net_profit_attributable_to_group`;
  `net_profit_attributable_to_group + brought_forward_profit ~=
  total_profit`.
- **Cash flow:** `operating + investing + financing + fx_translation ~=
  net_increase_in_cash`; `opening_cash + cash_acquired_on_amalgamation +
  net_increase_in_cash ~= closing_cash`.

All formulas were **hand-verified against the real 2017-2024 HDFC Bank
figures** before being encoded - not just internally consistent test
data. Three fields (`goodwill_on_consolidation`,
`addition_on_amalgamation`, `cash_acquired_on_amalgamation`) are one-off
reconciling items that only appear in years with a merger/amalgamation
event; these default to 0 when absent rather than making the whole check
`NOT_APPLICABLE`, since their absence is normal, not a sign of missed
extraction.

## 8. Database / persistence approach

A single `processed_documents` table (SQLite via SQLAlchemy): one row per
processing run, storing `document_name`, `document_type`,
`processing_status`, the full result as a JSON column, and a timestamp.
`GET /documents/{name}` queries the most recent row for that name (prior
versions are retained, not deleted). `GET /documents` lists recent rows
for the dashboard, which the frontend fetches client-side.

## 9. Known limitations and what I'd change for production

- **Gemini free-tier daily quota is low (20 requests/day for
  `gemini-3.6-flash`)** - discovered during real testing. An evaluator
  processing many documents in one sitting may hit `429
  RESOURCE_EXHAUSTED` through no fault of the code. Production would
  enable pay-as-you-go billing on the Google Cloud project, which removes
  this cap entirely.
- **Gemini model availability changes frequently** - this project
  actually hit a real mid-build deprecation of `gemini-2.0-flash`.
  `GEMINI_MODEL` is a configurable env var specifically so this is a
  one-line fix, not a code change, if it happens again.
- **SQLite on Render's free tier is not durable across redeploys** - the
  filesystem is ephemeral, so processed-document history resets on every
  redeploy. The code already supports Postgres via `DATABASE_URL` with
  zero other changes - this is the first thing to swap for production.
- **Single Gunicorn worker (with 4 threads)** - chosen after live
  debugging showed that multiple worker *processes* raced each other on
  SQLite table creation at startup, and that a single-threaded worker
  couldn't answer Render's own health check while busy with a 30-90
  second OCR/Gemini request (causing Render to kill and restart the
  container mid-processing). One process with several threads solves
  both problems, at the cost of true multi-process parallelism - an
  acceptable tradeoff for a solo-evaluator demo, not for real concurrent
  load. Production would use Postgres (safe for concurrent writers from
  multiple processes) and scale workers normally.
- **Financial validation formula scope** - validates against the
  *minimum required fields* per document type plus the real HDFC-specific
  fields discovered in testing, not every conceivable line item a
  different bank's statement might show. A production version would
  generalize the field/formula set further across more institutions'
  reporting formats.
- **No automated check that the model actually avoided inventing
  values** - relies on prompt instructions rather than a secondary
  verification pass. Production would add a grounding check that verifies
  each `source_text` snippet actually appears in the extracted document
  text.
- **No auth/rate limiting** - the API is open, appropriate for an
  evaluation deployment but not production multi-tenant use.
- **Synchronous processing only** - a slow document blocks the request
  for its full duration (up to ~90s observed on Render's free-tier CPU).
  The spec explicitly allows this for the assessment; production would
  move to an async job queue with a polling/webhook status endpoint.
- **Render free-tier cold starts** - the service sleeps after 15 minutes
  of inactivity; the first request after that can take up to a minute
  just to wake up, on top of normal processing time.

## 10. AI coding assistant usage declaration

This solution was built with Claude (Anthropic) as an AI pair-programmer
throughout the full 3-day build: architecture planning, writing all
backend services, the REST API layer, the Bootstrap/JS frontend, the
automated test suite, the Dockerfile and Render deployment config, the
architecture diagram, and this README. Claude was also used actively
during live deployment debugging - diagnosing a SQLite worker-startup
race condition, a Gunicorn health-check-starvation issue, and a
retry-logic bug (a 429 rate-limit response was silently never retried
because the Gemini SDK raises a different exception class for 4xx vs 5xx
errors than initially assumed) - each found and fixed by testing against
real live traffic, not just written and trusted by inspection. Design
decisions (stack choice, OCR strategy, validation scope, deployment
architecture) were made collaboratively and are explained with rationale
throughout this document and in code comments, per the assignment's
interview expectation that the candidate can explain, debug, and modify
anything submitted.

## 11. Repository structure

Matches the structure required by the assignment brief (`backend/app/{api,
core, models, schemas, services, repositories, utils}`, `frontend/`,
`docs/`, `sample_outputs/`) - see the top-level tree for the full layout.