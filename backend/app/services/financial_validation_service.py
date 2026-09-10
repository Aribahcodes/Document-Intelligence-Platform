"""
Financial calculation validation stage (spec section 4.4).

Each check returns: name, formula, operands, calculated_value,
reported_value, variance, status (PASS/FAIL/NOT_APPLICABLE). A check is
NOT_APPLICABLE whenever a required input field is genuinely missing -
we never assume or invent a value to force a PASS/FAIL.

For balance_sheet/profit_and_loss/cash_flow_statement, every check runs
TWICE - once for the current period, once for the prior period - since
the real dataset these formulas were verified against (HDFC Bank
consolidated statements) always shows two comparative periods. If a
document only has one period, the prior-period checks simply report
NOT_APPLICABLE (their inputs are null), not FAIL.

Three fields (goodwill_on_consolidation, addition_on_amalgamation,
cash_acquired_on_amalgamation) are one-off reconciling items that are
legitimately absent in most periods (see document_type_specs.py). These
are treated as 0 when null, NOT as NOT_APPLICABLE-triggering, since
their absence is normal, not a sign of missed extraction.
"""
from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)

_ZERO_DEFAULT_FIELDS = {
    "goodwill_on_consolidation",
    "addition_on_amalgamation",
    "cash_acquired_on_amalgamation",
}


def _num(extracted_data: dict, field: str):
    entry = extracted_data.get(field)
    if not entry:
        return None
    value = entry.get("value")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _num_default_zero(extracted_data: dict, field: str) -> float:
    value = _num(extracted_data, field)
    return value if value is not None else 0.0


def _check(name: str, formula: str, operands: dict, calculated, reported, tolerance=None):
    tolerance = tolerance if tolerance is not None else Config.VALIDATION_TOLERANCE

    if calculated is None or reported is None or any(v is None for v in operands.values()):
        return {
            "name": name,
            "formula": formula,
            "operands": operands,
            "calculated_value": calculated,
            "reported_value": reported,
            "variance": None,
            "status": "NOT_APPLICABLE",
        }

    variance = round(calculated - reported, 2)
    allowed = max(abs(reported) * tolerance, 0.01)
    status = "PASS" if abs(variance) <= allowed else "FAIL"

    return {
        "name": name,
        "formula": formula,
        "operands": operands,
        "calculated_value": round(calculated, 2),
        "reported_value": round(reported, 2),
        "variance": variance,
        "status": status,
    }


def _validate_invoice(extracted_data: dict, line_items: list) -> list:
    checks = []

    subtotal = _num(extracted_data, "subtotal")
    tax = _num(extracted_data, "tax_amount")
    discount = _num(extracted_data, "discount") or 0.0
    total = _num(extracted_data, "total_amount")

    checks.append(_check(
        "invoice_total_check",
        "subtotal + tax_amount - discount",
        {"subtotal": subtotal, "tax_amount": tax, "discount": discount},
        (subtotal + tax - discount) if (subtotal is not None and tax is not None) else None,
        total,
    ))

    if line_items:
        line_total_sum = 0.0
        all_valid = True
        for item in line_items:
            amount = item.get("amount")
            if amount is None:
                all_valid = False
                continue
            try:
                line_total_sum += float(amount)
            except (TypeError, ValueError):
                all_valid = False
        checks.append(_check(
            "line_items_sum_check",
            "sum(line_items.amount)",
            {"line_item_count": len(line_items)},
            line_total_sum if all_valid else None,
            subtotal if subtotal is not None else total,
        ))

        for idx, item in enumerate(line_items):
            qty, price, amount = item.get("quantity"), item.get("unit_price"), item.get("amount")
            if qty is None or price is None:
                continue
            try:
                calc = float(qty) * float(price)
            except (TypeError, ValueError):
                continue
            checks.append(_check(
                f"line_item_{idx + 1}_quantity_check",
                "quantity * unit_price",
                {"quantity": qty, "unit_price": price},
                calc,
                amount,
            ))

    cash_paid = _num(extracted_data, "cash_paid")
    change = _num(extracted_data, "change")
    if cash_paid is not None and total is not None:
        checks.append(_check(
            "cash_change_check", "cash_paid - total_amount",
            {"cash_paid": cash_paid, "total_amount": total},
            cash_paid - total, change,
        ))

    return checks


def _validate_balance_sheet_period(extracted_data: dict, prefix: str) -> list:
    def f(name):
        return _num(extracted_data, f"{prefix}{name}")

    def f0(name):
        return _num_default_zero(extracted_data, f"{prefix}{name}")

    capital = f("capital")
    esop = f("employees_stock_options")
    reserves = f("reserves_and_surplus")
    minority = f("minority_interest")
    deposits = f("deposits")
    borrowings = f("borrowings")
    other_liab = f("other_liabilities_and_provisions")
    policyholders = f0("policyholders_funds")
    total_liab = f("total_capital_and_liabilities")

    cash_rbi = f("cash_and_balances_with_rbi")
    bank_balances = f("balances_with_banks_and_money_at_call")
    investments = f("investments")
    advances = f("advances")
    fixed_assets = f("fixed_assets")
    other_assets = f("other_assets")
    goodwill = f0("goodwill_on_consolidation")
    total_assets = f("total_assets")

    liab_side_known = [capital, esop, reserves, minority, deposits, borrowings, other_liab]
    liab_sum = (sum(liab_side_known) + policyholders) if all(v is not None for v in liab_side_known) else None

    asset_side_known = [cash_rbi, bank_balances, investments, advances, fixed_assets, other_assets]
    asset_sum = (sum(asset_side_known) + goodwill) if all(v is not None for v in asset_side_known) else None

    checks = [
        _check(
            f"{prefix}capital_and_liabilities_total_check",
            "capital + esop + reserves_and_surplus + minority_interest + deposits + "
            "borrowings + other_liabilities_and_provisions + policyholders_funds",
            {"capital": capital, "employees_stock_options": esop, "reserves_and_surplus": reserves,
             "minority_interest": minority, "deposits": deposits, "borrowings": borrowings,
             "other_liabilities_and_provisions": other_liab},
            liab_sum, total_liab,
        ),
        _check(
            f"{prefix}assets_total_check",
            "cash_and_balances_with_rbi + balances_with_banks_and_money_at_call + investments + "
            "advances + fixed_assets + other_assets + goodwill_on_consolidation",
            {"cash_and_balances_with_rbi": cash_rbi, "balances_with_banks_and_money_at_call": bank_balances,
             "investments": investments, "advances": advances, "fixed_assets": fixed_assets,
             "other_assets": other_assets},
            asset_sum, total_assets,
        ),
        _check(
            f"{prefix}balance_sheet_equation_check",
            "total_capital_and_liabilities == total_assets",
            {"total_capital_and_liabilities": total_liab},
            total_liab, total_assets,
        ),
    ]
    return checks


def _validate_profit_and_loss_period(extracted_data: dict, prefix: str) -> list:
    def f(name):
        return _num(extracted_data, f"{prefix}{name}")

    def f0(name):
        return _num_default_zero(extracted_data, f"{prefix}{name}")

    interest_earned = f("interest_earned")
    other_income = f("other_income")
    total_income = f("total_income")

    interest_expended = f("interest_expended")
    operating_expenses = f("operating_expenses")
    provisions = f("provisions_and_contingencies")
    total_expenditure = f("total_expenditure")

    net_profit_before_minority = f("net_profit_before_minority_interest")
    minority = f("minority_interest")
    net_profit_group = f("net_profit_attributable_to_group")
    brought_forward = f("brought_forward_profit")
    amalgamation = f0("addition_on_amalgamation")
    total_profit = f("total_profit")

    checks = [
        _check(
            f"{prefix}total_income_check", "interest_earned + other_income",
            {"interest_earned": interest_earned, "other_income": other_income},
            (interest_earned + other_income) if (interest_earned is not None and other_income is not None) else None,
            total_income,
        ),
        _check(
            f"{prefix}total_expenditure_check",
            "interest_expended + operating_expenses + provisions_and_contingencies",
            {"interest_expended": interest_expended, "operating_expenses": operating_expenses,
             "provisions_and_contingencies": provisions},
            (interest_expended + operating_expenses + provisions)
            if all(v is not None for v in [interest_expended, operating_expenses, provisions]) else None,
            total_expenditure,
        ),
        _check(
            f"{prefix}net_profit_before_minority_check",
            "total_income - total_expenditure",
            {"total_income": total_income, "total_expenditure": total_expenditure},
            (total_income - total_expenditure) if (total_income is not None and total_expenditure is not None) else None,
            net_profit_before_minority,
        ),
        _check(
            f"{prefix}net_profit_attributable_to_group_check",
            "net_profit_before_minority_interest - minority_interest",
            {"net_profit_before_minority_interest": net_profit_before_minority, "minority_interest": minority},
            (net_profit_before_minority - minority)
            if (net_profit_before_minority is not None and minority is not None) else None,
            net_profit_group,
        ),
        _check(
            f"{prefix}total_profit_check",
            "net_profit_attributable_to_group + brought_forward_profit + addition_on_amalgamation",
            {"net_profit_attributable_to_group": net_profit_group, "brought_forward_profit": brought_forward},
            (net_profit_group + brought_forward + amalgamation)
            if (net_profit_group is not None and brought_forward is not None) else None,
            total_profit,
        ),
    ]
    return checks


def _validate_cash_flow_period(extracted_data: dict, prefix: str) -> list:
    def f(name):
        return _num(extracted_data, f"{prefix}{name}")

    def f0(name):
        return _num_default_zero(extracted_data, f"{prefix}{name}")

    operating = f("net_cash_from_operating_activities")
    investing = f("net_cash_from_investing_activities")
    financing = f("net_cash_from_financing_activities")
    fx_effect = f0("effect_of_fx_translation")
    net_increase = f("net_increase_in_cash")

    beginning = f("cash_at_beginning")
    acquired = f0("cash_acquired_on_amalgamation")
    end = f("cash_at_end")

    checks = [
        _check(
            f"{prefix}net_increase_in_cash_check",
            "net_cash_from_operating_activities + net_cash_from_investing_activities + "
            "net_cash_from_financing_activities + effect_of_fx_translation",
            {"net_cash_from_operating_activities": operating, "net_cash_from_investing_activities": investing,
             "net_cash_from_financing_activities": financing},
            (operating + investing + financing + fx_effect)
            if all(v is not None for v in [operating, investing, financing]) else None,
            net_increase,
        ),
        _check(
            f"{prefix}cash_at_end_check",
            "cash_at_beginning + cash_acquired_on_amalgamation + net_increase_in_cash",
            {"cash_at_beginning": beginning, "net_increase_in_cash": net_increase},
            (beginning + acquired + net_increase) if (beginning is not None and net_increase is not None) else None,
            end,
        ),
    ]
    return checks


def _validate_balance_sheet(extracted_data: dict, line_items: list) -> list:
    return _validate_balance_sheet_period(extracted_data, "current_") + \
        _validate_balance_sheet_period(extracted_data, "prior_")


def _validate_profit_and_loss(extracted_data: dict, line_items: list) -> list:
    return _validate_profit_and_loss_period(extracted_data, "current_") + \
        _validate_profit_and_loss_period(extracted_data, "prior_")


def _validate_cash_flow(extracted_data: dict, line_items: list) -> list:
    return _validate_cash_flow_period(extracted_data, "current_") + \
        _validate_cash_flow_period(extracted_data, "prior_")


_VALIDATORS = {
    "invoice": _validate_invoice,
    "balance_sheet": _validate_balance_sheet,
    "profit_and_loss": _validate_profit_and_loss,
    "cash_flow_statement": _validate_cash_flow,
}


def validate(document_type: str, extracted_data: dict, line_items: list) -> dict:
    validator = _VALIDATORS.get(document_type)
    if not validator:
        return {"checks": [], "overall_status": "NOT_APPLICABLE", "issues": []}

    checks = validator(extracted_data, line_items or [])

    statuses = {c["status"] for c in checks}
    if "FAIL" in statuses:
        overall = "FAIL"
    elif statuses == {"NOT_APPLICABLE"} or not statuses:
        overall = "NOT_APPLICABLE"
    else:
        overall = "PASS"

    issues = [f"{c['name']} failed: expected {c['reported_value']}, calculated {c['calculated_value']}"
              for c in checks if c["status"] == "FAIL"]

    logger.info("Financial validation for %s: overall_status=%s (%d checks)",
                document_type, overall, len(checks))

    return {"checks": checks, "overall_status": overall, "issues": issues}
