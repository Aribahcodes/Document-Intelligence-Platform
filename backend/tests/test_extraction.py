"""
Tests for extraction_service. The actual Gemini API call is mocked so
these tests run offline, instantly, and consume zero API quota - they
verify our prompt construction, response parsing, null-handling, and
retry behavior, not Gemini itself.

The retry tests are not incidental - roughly 1 in 4 real calls hit a
transient 503 during this project's development, and a real 429 bug
(rate limits were silently never retried, despite being listed as
retryable, because google-genai raises ClientError for 429 rather than
ServerError) was only caught by testing against live traffic. These
tests exist so that class of regression can never silently reappear.
"""
import json
import time
from unittest.mock import MagicMock, patch

from google.genai import errors as genai_errors

from app.services import extraction_service as es


def _fake_gemini_response(payload: dict):
    mock_response = MagicMock()
    mock_response.text = json.dumps(payload)
    return mock_response


@patch("app.services.extraction_service._get_client")
def test_extract_fields_parses_valid_json_response(mock_get_client):
    payload = {
        "extracted_data": {
            "invoice_number": {"value": "INV-1001", "page_number": 1, "source_text": "Invoice Number: INV-1001"},
            "vendor_name": {"value": "ABC Technologies", "page_number": 1, "source_text": "Vendor: ABC Technologies"},
        },
        "line_items": [
            {"description": "Service A", "quantity": 1, "unit_price": 12500.0, "amount": 12500.0}
        ],
    }
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _fake_gemini_response(payload)
    mock_get_client.return_value = mock_client

    ocr_result = {"full_text": "[Page 1]\nInvoice Number: INV-1001\nVendor: ABC Technologies"}
    result = es.extract_fields("invoice", ocr_result)

    assert result["extracted_data"]["invoice_number"]["value"] == "INV-1001"
    assert len(result["line_items"]) == 1


@patch("app.services.extraction_service._get_client")
def test_extract_fields_handles_missing_values_as_null(mock_get_client):
    payload = {
        "extracted_data": {
            "invoice_number": {"value": "INV-1001", "page_number": 1, "source_text": "..."},
            "discount": {"value": None, "page_number": None, "source_text": None},
        },
        "line_items": [],
    }
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _fake_gemini_response(payload)
    mock_get_client.return_value = mock_client

    result = es.extract_fields("invoice", {"full_text": "some text"})
    assert result["extracted_data"]["discount"]["value"] is None


def test_extract_fields_returns_empty_when_no_text():
    result = es.extract_fields("invoice", {"full_text": ""})
    assert result["extracted_data"] == {}
    assert result["line_items"] == []


@patch("app.services.extraction_service._get_client")
def test_extract_fields_handles_markdown_fenced_json(mock_get_client):
    """Model sometimes wraps output in ```json fences despite instructions not to."""
    fenced = "```json\n" + json.dumps({"extracted_data": {"total_amount": {"value": 100.0}}, "line_items": []}) + "\n```"
    mock_response = MagicMock()
    mock_response.text = fenced
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = es.extract_fields("invoice", {"full_text": "some text"})
    assert result["extracted_data"]["total_amount"]["value"] == 100.0


@patch("app.services.extraction_service.time.sleep")  # skip real waiting in tests
@patch("app.services.extraction_service._get_client")
def test_retries_on_transient_503_then_succeeds(mock_get_client, mock_sleep):
    server_err = genai_errors.ServerError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}})
    success = _fake_gemini_response({"extracted_data": {}, "line_items": []})
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [server_err, success]
    mock_get_client.return_value = mock_client

    es.extract_fields("invoice", {"full_text": "some text"})
    assert mock_client.models.generate_content.call_count == 2


@patch("app.services.extraction_service.time.sleep")
@patch("app.services.extraction_service._get_client")
def test_retries_on_429_rate_limit_then_succeeds(mock_get_client, mock_sleep):
    """
    Regression test for a real bug found via live testing: google-genai
    raises ClientError (not ServerError) for HTTP 429, so an earlier
    version of this code that only caught ServerError silently never
    retried rate-limit responses despite 429 being listed as retryable.
    """
    rate_limit_err = genai_errors.ClientError(429, {"error": {"message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}})
    success = _fake_gemini_response({"extracted_data": {}, "line_items": []})
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [rate_limit_err, rate_limit_err, success]
    mock_get_client.return_value = mock_client

    es.extract_fields("invoice", {"full_text": "some text"})
    assert mock_client.models.generate_content.call_count == 3


@patch("app.services.extraction_service.time.sleep")
@patch("app.services.extraction_service._get_client")
def test_does_not_retry_non_retryable_client_error(mock_get_client, mock_sleep):
    """A 401 (bad API key) must fail immediately - retrying it can never succeed."""
    from app.utils.exceptions import ExtractionModelError
    import pytest

    auth_err = genai_errors.ClientError(401, {"error": {"message": "bad key", "status": "UNAUTHENTICATED"}})
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [auth_err]
    mock_get_client.return_value = mock_client

    with pytest.raises(ExtractionModelError):
        es.extract_fields("invoice", {"full_text": "some text"})
    assert mock_client.models.generate_content.call_count == 1


@patch("app.services.extraction_service.time.sleep")
@patch("app.services.extraction_service._get_client")
def test_gives_up_after_max_attempts_on_persistent_failure(mock_get_client, mock_sleep):
    from app.utils.exceptions import ExtractionModelError
    import pytest

    server_err = genai_errors.ServerError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}})
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [server_err, server_err, server_err]
    mock_get_client.return_value = mock_client

    with pytest.raises(ExtractionModelError):
        es.extract_fields("invoice", {"full_text": "some text"})
    assert mock_client.models.generate_content.call_count == 3
