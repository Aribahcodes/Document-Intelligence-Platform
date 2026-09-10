"""
Per-document-type field definitions used by extraction prompts.

For invoices, minimum_fields is a flat list. For the three financial
statement types (balance_sheet, profit_and_loss, cash_flow_statement),
every field appears twice - prefixed current_ and prior_ - because the
real dataset these were designed against (HDFC Bank consolidated
statements) always shows two comparative periods side by side (e.g.
"As at March 31, 2024" and "As at March 31, 2023"). If a given document
only shows one period, prior_* fields simply come back null, and any
validation checks depending on them report NOT_APPLICABLE rather than
FAIL - see financial_validation_service.py.
"""

DOCUMENT_TYPES = {
    "invoice": {
        "minimum_fields": [
            "invoice_number", "invoice_date", "vendor_name", "customer_name",
            "currency", "subtotal", "tax_amount", "discount", "total_amount",
        ],
        "has_line_items": True,
        "has_comparative_periods": False,
        "description": "A commercial invoice or retail tax invoice/receipt, possibly with a line-item table.",
    },

    "balance_sheet": {
        "minimum_fields": [
            "period_end_date_current", "period_end_date_prior", "currency_unit",
            "current_capital", "current_reserves_and_surplus", "current_minority_interest",
            "current_deposits", "current_borrowings", "current_other_liabilities_and_provisions",
            "current_total_capital_and_liabilities",
            "prior_capital", "prior_reserves_and_surplus", "prior_minority_interest",
            "prior_deposits", "prior_borrowings", "prior_other_liabilities_and_provisions",
            "prior_total_capital_and_liabilities",
            "current_cash_and_balances_with_rbi", "current_balances_with_banks_and_money_at_call",
            "current_investments", "current_advances", "current_fixed_assets", "current_other_assets",
            "current_total_assets",
            "prior_cash_and_balances_with_rbi", "prior_balances_with_banks_and_money_at_call",
            "prior_investments", "prior_advances", "prior_fixed_assets", "prior_other_assets",
            "prior_total_assets",
        ],
        "has_line_items": False,
        "has_comparative_periods": True,
        "description": (
            "A bank-format consolidated balance sheet, structured as 'Capital and Liabilities' "
            "(Capital, Reserves and Surplus, Minority Interest, Deposits, Borrowings, Other "
            "Liabilities and Provisions) versus 'Assets' (Cash and balances with RBI, Balances with "
            "banks, Investments, Advances, Fixed Assets, Other Assets), each side totaling to the "
            "same figure. Shows two comparative periods (current year and prior year) side by side."
        ),
    },

    "profit_and_loss": {
        "minimum_fields": [
            "period_current", "period_prior", "currency_unit",
            "current_interest_earned", "current_other_income", "current_total_income",
            "prior_interest_earned", "prior_other_income", "prior_total_income",
            "current_interest_expended", "current_operating_expenses", "current_provisions_and_contingencies",
            "current_total_expenditure",
            "prior_interest_expended", "prior_operating_expenses", "prior_provisions_and_contingencies",
            "prior_total_expenditure",
            "current_net_profit_before_minority_interest", "current_minority_interest",
            "current_net_profit_attributable_to_group", "current_brought_forward_profit",
            "current_total_profit",
            "prior_net_profit_before_minority_interest", "prior_minority_interest",
            "prior_net_profit_attributable_to_group", "prior_brought_forward_profit",
            "prior_total_profit",
            "current_basic_eps", "current_diluted_eps", "prior_basic_eps", "prior_diluted_eps",
        ],
        "has_line_items": True,
        "has_comparative_periods": True,
        "description": (
            "A bank-format consolidated Profit and Loss account with sections: Income (Interest "
            "Earned, Other Income), Expenditure (Interest Expended, Operating Expenses, Provisions "
            "and Contingencies), Profit (before and after Minority Interest), Appropriations "
            "(transfers to various reserves, dividends), and Earnings Per Share. Shows two "
            "comparative periods (current year and prior year) side by side."
        ),
    },

    "cash_flow_statement": {
        "minimum_fields": [
            "period_current", "period_prior", "currency_unit",
            "current_net_cash_from_operating_activities", "current_net_cash_from_investing_activities",
            "current_net_cash_from_financing_activities", "current_effect_of_fx_translation",
            "current_net_increase_in_cash", "current_cash_at_beginning", "current_cash_at_end",
            "prior_net_cash_from_operating_activities", "prior_net_cash_from_investing_activities",
            "prior_net_cash_from_financing_activities", "prior_effect_of_fx_translation",
            "prior_net_increase_in_cash", "prior_cash_at_beginning", "prior_cash_at_end",
        ],
        "has_line_items": True,
        "has_comparative_periods": True,
        "description": (
            "A bank-format consolidated Cash Flow Statement with sections: Cash flows from "
            "operating activities, investing activities, and financing activities, an effect of "
            "foreign currency translation, and a reconciliation of cash at the beginning versus end "
            "of the period. Shows two comparative periods (current year and prior year) side by side."
        ),
    },
}


def is_valid_document_type(document_type: str) -> bool:
    return document_type in DOCUMENT_TYPES
