"""
API flow tests (spec section 11: "at least basic automated tests for
... one API flow"). Uses an isolated temporary SQLite database per test
run and mocks the Gemini call, so the suite runs offline, fast, and
consumes zero API quota.
"""
import io
import os

import pytest

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("APP_ENV", "testing")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    from app.main import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _make_pdf_bytes():
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Invoice Number: INV-1001")
    page.insert_text((72, 100), "Total Amount Due: USD 13125.00")
    return doc.tobytes()


def test_health_endpoint(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_list_documents_empty(client):
    resp = client.get("/api/v1/documents")
    assert resp.status_code == 200
    assert resp.get_json() == {"documents": []}


def test_get_nonexistent_document_returns_404(client):
    resp = client.get("/api/v1/documents/does_not_exist.pdf")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_process_rejects_missing_file(client):
    resp = client.post("/api/v1/documents/process", data={"document_type": "invoice"},
                        content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "MISSING_FILE"


def test_process_rejects_unsupported_file_type(client):
    data = {
        "file": (io.BytesIO(b"not a real document"), "notes.txt"),
        "document_type": "invoice",
    }
    resp = client.post("/api/v1/documents/process", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_process_rejects_empty_file(client):
    data = {
        "file": (io.BytesIO(b""), "empty.pdf"),
        "document_type": "invoice",
    }
    resp = client.post("/api/v1/documents/process", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "EMPTY_OR_CORRUPTED_FILE"


def test_process_rejects_invalid_document_type(client):
    data = {
        "file": (io.BytesIO(_make_pdf_bytes()), "invoice.pdf"),
        "document_type": "not_a_real_type",
    }
    resp = client.post("/api/v1/documents/process", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_DOCUMENT_TYPE"


def test_full_process_flow_with_mocked_extraction(client, monkeypatch):
    """
    End-to-end flow required by spec section 11: upload -> process ->
    appears in list -> retrievable by name. The Gemini call is mocked
    so this runs offline, deterministically, with zero API quota used.
    """
    fake_extraction = {
        "extracted_data": {
            "invoice_number": {"value": "INV-1001", "page_number": 1, "source_text": "Invoice Number: INV-1001"},
            "subtotal": {"value": 12500.0, "page_number": 1, "source_text": "Subtotal: 12500.00"},
            "tax_amount": {"value": 625.0, "page_number": 1, "source_text": "Tax: 625.00"},
            "discount": {"value": 0.0, "page_number": 1, "source_text": None},
            "total_amount": {"value": 13125.0, "page_number": 1, "source_text": "Total Amount Due: USD 13125.00"},
        },
        "line_items": [],
    }
    monkeypatch.setattr(
        "app.services.document_service.extraction_service.extract_fields",
        lambda document_type, ocr_result: fake_extraction,
    )

    data = {
        "file": (io.BytesIO(_make_pdf_bytes()), "test_invoice.pdf"),
        "document_type": "invoice",
    }
    process_resp = client.post("/api/v1/documents/process", data=data, content_type="multipart/form-data")
    assert process_resp.status_code == 200
    body = process_resp.get_json()
    assert body["document_name"] == "test_invoice.pdf"
    assert body["processing_status"] == "PASS"
    assert body["validation"]["overall_status"] == "PASS"
    assert body["extracted_data"]["invoice_number"]["value"] == "INV-1001"

    list_resp = client.get("/api/v1/documents")
    names = [d["document_name"] for d in list_resp.get_json()["documents"]]
    assert "test_invoice.pdf" in names

    get_resp = client.get("/api/v1/documents/test_invoice.pdf")
    assert get_resp.status_code == 200
    assert get_resp.get_json()["processing_status"] == "PASS"


def test_reprocessing_same_document_returns_latest_result(client, monkeypatch):
    """Per spec 5.1: if the same document name is processed more than
    once, GET-by-name should return the latest result."""
    call_count = {"n": 0}

    def fake_extract(document_type, ocr_result):
        call_count["n"] += 1
        total = 13125.0 if call_count["n"] == 1 else 99999.0
        return {
            "extracted_data": {"total_amount": {"value": total, "page_number": 1, "source_text": None}},
            "line_items": [],
        }

    monkeypatch.setattr("app.services.document_service.extraction_service.extract_fields", fake_extract)

    data = {"file": (io.BytesIO(_make_pdf_bytes()), "repeat.pdf"), "document_type": "invoice"}
    client.post("/api/v1/documents/process", data=data, content_type="multipart/form-data")

    data2 = {"file": (io.BytesIO(_make_pdf_bytes()), "repeat.pdf"), "document_type": "invoice"}
    client.post("/api/v1/documents/process", data=data2, content_type="multipart/form-data")

    get_resp = client.get("/api/v1/documents/repeat.pdf")
    assert get_resp.get_json()["extracted_data"]["total_amount"]["value"] == 99999.0
