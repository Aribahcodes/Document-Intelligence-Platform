"""
Tests for both validation stages required by the spec:
- File/document validation - input-control layer (section 4.1)
- Financial calculation validation (section 4.4)

Pure unit tests - no Flask app, no database, no external API calls.
"""
import fitz
import pytest

from app.services import document_validation_service as dvs
from app.services import financial_validation_service as fvs
from app.utils.exceptions import (
    EmptyOrCorruptedFileError,
    PageLimitExceededError,
    UnsupportedFileTypeError,
)


def _field(value):
    return {"value": value, "page_number": 1, "source_text": "test"}


# --- File / document validation (spec section 4.1) ---

def _make_pdf_bytes(num_pages=1):
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1}")
    return doc.tobytes()


def test_valid_single_page_pdf():
    result = dvs.validate_file("invoice.pdf", _make_pdf_bytes(1))
    assert result["status"] == "PASS"
    assert result["file_type"] == "application/pdf"
    assert result["page_count"] == 1


def test_valid_three_page_pdf_is_within_limit():
    result = dvs.validate_file("statement.pdf", _make_pdf_bytes(3))
    assert result["status"] == "PASS"
    assert result["page_count"] == 3


def test_four_page_pdf_exceeds_limit():
    with pytest.raises(PageLimitExceededError):
        dvs.validate_file("too_long.pdf", _make_pdf_bytes(4))


def test_empty_file_rejected():
    with pytest.raises(EmptyOrCorruptedFileError):
        dvs.validate_file("empty.pdf", b"")


def test_unsupported_file_type_rejected():
    with pytest.raises(UnsupportedFileTypeError):
        dvs.validate_file("notes.txt", b"just some plain text, not a real document")


def test_corrupted_pdf_rejected():
    with pytest.raises(EmptyOrCorruptedFileError):
        dvs.validate_file("corrupted.pdf", b"%PDF-1.4\nthis is not a real pdf body" + bytes(50))


# --- Financial validation (spec section 4.4) - formulas hand-verified
# against real HDFC Bank 2017-2024 consolidated statements ---

def test_invoice_total_check_pass():
    data = {
        "subtotal": _field(12500.00),
        "tax_amount": _field(625.00),
        "discount": _field(0.00),
        "total_amount": _field(13125.00),
    }
    result = fvs.validate("invoice", data, line_items=[])
    check = next(c for c in result["checks"] if c["name"] == "invoice_total_check")
    assert check["status"] == "PASS"
    assert check["calculated_value"] == 13125.00
    assert result["overall_status"] == "PASS"


def test_invoice_total_check_fail():
    data = {
        "subtotal": _field(12500.00),
        "tax_amount": _field(625.00),
        "discount": _field(0.00),
        "total_amount": _field(99999.00),  # wrong total, on purpose
    }
    result = fvs.validate("invoice", data, line_items=[])
    check = next(c for c in result["checks"] if c["name"] == "invoice_total_check")
    assert check["status"] == "FAIL"
    assert result["overall_status"] == "FAIL"
    assert len(result["issues"]) >= 1


def test_invoice_missing_field_is_not_applicable():
    data = {
        "subtotal": _field(None),  # not present in the document
        "tax_amount": _field(625.00),
        "total_amount": _field(13125.00),
    }
    result = fvs.validate("invoice", data, line_items=[])
    check = next(c for c in result["checks"] if c["name"] == "invoice_total_check")
    assert check["status"] == "NOT_APPLICABLE"


def test_invoice_line_item_quantity_check():
    data = {"subtotal": _field(12500.00), "tax_amount": _field(625.00),
            "discount": _field(0.0), "total_amount": _field(13125.00)}
    line_items = [{"description": "Service A", "quantity": 2, "unit_price": 6250.00, "amount": 12500.00}]
    result = fvs.validate("invoice", data, line_items)
    check = next(c for c in result["checks"] if "quantity_check" in c["name"])
    assert check["status"] == "PASS"


def test_balance_sheet_real_2024_figures_pass():
    """Hand-verified against the real Consolidated Balance Sheet 2024.pdf."""
    data = {
        "current_capital": _field(759.69), "current_employees_stock_options": _field(2652.72),
        "current_reserves_and_surplus": _field(452982.84), "current_minority_interest": _field(13383.40),
        "current_deposits": _field(2376887.28), "current_borrowings": _field(730615.46),
        "current_other_liabilities_and_provisions": _field(174832.07), "current_policyholders_funds": _field(278080.80),
        "current_total_capital_and_liabilities": _field(4030194.26),
        "current_cash_and_balances_with_rbi": _field(178718.67), "current_balances_with_banks_and_money_at_call": _field(50115.84),
        "current_investments": _field(1005681.63), "current_advances": _field(2565891.41),
        "current_fixed_assets": _field(12603.76), "current_other_assets": _field(217182.95),
        "current_goodwill_on_consolidation": _field(0), "current_total_assets": _field(4030194.26),
    }
    result = fvs.validate("balance_sheet", data, line_items=[])
    current_checks = [c for c in result["checks"] if c["name"].startswith("current_")]
    assert all(c["status"] == "PASS" for c in current_checks)


def test_balance_sheet_equation_fail_on_bad_data():
    data = {
        "current_capital": _field(759.69), "current_employees_stock_options": _field(2652.72),
        "current_reserves_and_surplus": _field(452982.84), "current_minority_interest": _field(13383.40),
        "current_deposits": _field(2376887.28), "current_borrowings": _field(730615.46),
        "current_other_liabilities_and_provisions": _field(174832.07), "current_policyholders_funds": _field(278080.80),
        "current_total_capital_and_liabilities": _field(9999999.99),  # deliberately wrong
    }
    result = fvs.validate("balance_sheet", data, line_items=[])
    check = next(c for c in result["checks"] if c["name"] == "current_capital_and_liabilities_total_check")
    assert check["status"] == "FAIL"


def test_profit_and_loss_real_2024_figures_pass():
    """Hand-verified against the real Consolidated Profit & Loss 2024.pdf."""
    data = {
        "current_interest_earned": _field(283649.02), "current_other_income": _field(124345.75),
        "current_total_income": _field(407994.77),
        "current_interest_expended": _field(154138.55), "current_operating_expenses": _field(152269.34),
        "current_provisions_and_contingencies": _field(36140.38), "current_total_expenditure": _field(342548.27),
        "current_net_profit_before_minority_interest": _field(65446.50), "current_minority_interest": _field(1384.46),
        "current_net_profit_attributable_to_group": _field(64062.04), "current_brought_forward_profit": _field(120369.35),
        "current_addition_on_amalgamation": _field(3570.10), "current_total_profit": _field(188001.49),
    }
    result = fvs.validate("profit_and_loss", data, line_items=[])
    current_checks = [c for c in result["checks"] if c["name"].startswith("current_")]
    assert all(c["status"] == "PASS" for c in current_checks)


def test_cash_flow_real_2024_figures_pass():
    """Hand-verified against the real Consolidated Cash Flow Statement 2024.pdf."""
    data = {
        "current_net_cash_from_operating_activities": _field(19069.34),
        "current_net_cash_from_investing_activities": _field(5313.77),
        "current_net_cash_from_financing_activities": _field(-3983.06),
        "current_effect_of_fx_translation": _field(104.94),
        "current_net_increase_in_cash": _field(20504.99),
        "current_cash_at_beginning": _field(197147.81),
        "current_cash_acquired_on_amalgamation": _field(11181.71),
        "current_cash_at_end": _field(228834.51),
    }
    result = fvs.validate("cash_flow_statement", data, line_items=[])
    current_checks = [c for c in result["checks"] if c["name"].startswith("current_")]
    assert all(c["status"] == "PASS" for c in current_checks)


def test_single_period_document_prior_checks_are_not_applicable():
    """A document with only one period's data should not FAIL on the missing prior period."""
    data = {
        "current_interest_earned": _field(283649.02), "current_other_income": _field(124345.75),
        "current_total_income": _field(407994.77),
        "current_interest_expended": _field(154138.55), "current_operating_expenses": _field(152269.34),
        "current_provisions_and_contingencies": _field(36140.38), "current_total_expenditure": _field(342548.27),
        "current_net_profit_before_minority_interest": _field(65446.50), "current_minority_interest": _field(1384.46),
        "current_net_profit_attributable_to_group": _field(64062.04), "current_brought_forward_profit": _field(120369.35),
        "current_addition_on_amalgamation": _field(3570.10), "current_total_profit": _field(188001.49),
        # no prior_* fields at all
    }
    result = fvs.validate("profit_and_loss", data, line_items=[])
    prior_checks = [c for c in result["checks"] if c["name"].startswith("prior_")]
    assert all(c["status"] == "NOT_APPLICABLE" for c in prior_checks)
    assert result["overall_status"] == "PASS"


def test_unknown_document_type_returns_not_applicable():
    result = fvs.validate("unknown_type", {}, [])
    assert result["overall_status"] == "NOT_APPLICABLE"
    assert result["checks"] == []
