# Document Intelligence Platform

An AI-powered document extraction and validation platform for financial
documents (invoices, balance sheets, profit & loss statements, cash flow
statements). Built for the AI Engineer Internship technical case study.

- **Live frontend:** `<TODO - fill in after deploying>`
- **Live backend API:** `<TODO - fill in after deploying>`
- **Swagger / OpenAPI docs:** `<TODO>/docs`
- **Health check:** `<TODO>/api/v1/health`
- **GitHub repository:** `<TODO - this repo's public URL>`

---

## 1. Solution overview

The platform accepts a PDF/JPG/PNG financial document through a web
dashboard or directly via a REST API, and runs it through a pipeline:

```
Upload
  ↓
File validation (PDF/JPG/PNG, integrity, page limit)
  ↓
Text extraction / OCR
  ↓
AI field extraction
  ↓
Financial validation
  ↓
Store result
  ↓
PASS / FAILED
  ↓
Dashboard + REST API
```

See [`docs/architecture.png`](docs/architecture.png) for the full component
diagram. In short: a single Flask application serves both the HTML
dashboard and the REST API, backed by SQLite, with Gemini used for the
AI extraction step.

## 2. Technology stack and why

| Concern | Choice | Why |
|---|---|---|
| Backend framework | **Flask** + flask-smorest | Lightweight, spec explicitly allows Flask; flask-smorest gives auto-generated Swagger/OpenAPI docs (`/docs`) for free |
| Text extraction / OCR | **PyMuPDF** (native PDF text layer) + **Tesseract** (fallback for scanned pages/images) | Native-PDF text extraction is fast and has zero OCR error rate; Tesseract is free, needs no API key, and runs entirely offline. Each *page* is judged independently, so a PDF that mixes native and scanned pages is handled correctly. |
| Field extraction (AI) | **Gemini API** (`gemini-2.0-flash` by default) | Generous free tier, strong structured-JSON output, low latency. |
| Database | **SQLite** via SQLAlchemy | Zero setup, file-based, meets the spec's minimum bar. `DATABASE_URL` is the only thing that needs to change to point at Postgres/MySQL instead. |
| Frontend | **Server-rendered Jinja2 + vanilla JS** (no build step) | The spec explicitly says a separate React/Node stack isn't required. |
| Deployment | **Docker on Render** | Tesseract is a system package, not a pip package, so the deployment platform needs Docker support. |

## 3. Local setup instructions

**Prerequisites:** Python 3.10+, Tesseract OCR installed locally, a Gemini API key.

```bash
git clone <this-repo-url>
cd document-intelligence-platform

cp .env.example .env
# edit .env: set GEMINI_API_KEY at minimum

cd backend
pip install -r requirements.txt
python -m app.main
# -> serves on http://localhost:8000
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

## 4. Environment variables

See [`.env.example`](.env.example) for the full list. The two that matter most:

- `GEMINI_API_KEY` - required for extraction. Get one at https://aistudio.google.com/apikey
- `DATABASE_URL` - defaults to local SQLite; set to a Postgres URL for production.

No secrets are hardcoded anywhere - `app/core/config.py` reads everything
from the environment, and `.env` is git-ignored.

## 5. API reference

Full interactive documentation is at `/docs` (Swagger UI) on the deployed instance.

- `POST /api/v1/documents/process` - upload and process a document
- `GET /api/v1/documents/{document_name}` - latest result by name
- `GET /api/v1/documents` - list processed documents
- `GET /api/v1/health` - health check

<!-- TODO: fill in detailed request/response examples once the API is built -->

## 6. Known limitations and production improvements

<!-- TODO: fill in once the full pipeline is built -->

## 7. AI coding assistant usage declaration

<!-- TODO: fill in your actual AI tool usage here -->