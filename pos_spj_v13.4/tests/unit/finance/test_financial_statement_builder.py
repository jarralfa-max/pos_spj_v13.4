"""Financial statement builder — accounting equation and statement math."""

import pytest

from backend.domain.finance.enums import AccountType, CashFlowCategory, NormalBalance
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.financial_statement_builder import (
    AccountBalanceRow,
    FinancialStatementBuilder,
)
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _row(code, name, acc_type, debits, credits, cf=CashFlowCategory.NONE):
    from backend.domain.finance.enums import NORMAL_BALANCE_BY_TYPE
    return AccountBalanceRow(
        account_id=new_uuid(), account_code=code, account_name=name,
        account_type=acc_type, normal_balance=NORMAL_BALANCE_BY_TYPE[acc_type],
        total_debits=Money.from_string(debits), total_credits=Money.from_string(credits),
        cash_flow_category=cf,
    )


@pytest.fixture
def builder():
    return FinancialStatementBuilder()


@pytest.fixture
def balanced_rows():
    # Cash sale 1000 with COGS 600: Dr Cash 1000 / Cr Revenue 1000; Dr COGS 600 / Cr Inventory 600
    return [
        _row("1101", "Caja", AccountType.ASSET, "1000.00", "0.00", CashFlowCategory.OPERATING),
        _row("1151", "Inventario", AccountType.ASSET, "0.00", "600.00"),
        _row("4101", "Ingresos por ventas", AccountType.REVENUE, "0.00", "1000.00"),
        _row("5101", "Costo de ventas", AccountType.COST_OF_SALES, "600.00", "0.00"),
    ]


class TestTrialBalance:
    def test_balanced_trial_balance(self, builder, balanced_rows):
        rows = builder.trial_balance(balanced_rows)
        assert len(rows) == 4
        assert rows[0].account_code == "1101"

    def test_unbalanced_trial_balance_raises(self, builder):
        rows = [_row("1101", "Caja", AccountType.ASSET, "100.00", "0.00")]
        with pytest.raises(FinanceDomainError):
            builder.trial_balance(rows)


class TestStatements:
    def test_income_statement(self, builder, balanced_rows):
        result = builder.income_statement(balanced_rows)
        assert result["net_revenue"] == "1000.00"
        assert result["cost_of_sales"] == "600.00"
        assert result["gross_profit"] == "400.00"
        assert result["net_income"] == "400.00"

    def test_balance_sheet_validates_equation(self, builder, balanced_rows):
        result = builder.balance_sheet(balanced_rows)
        assert result["assets"] == "400.00"          # 1000 cash - 600 inventory
        assert result["period_net_income"] == "400.00"
        assert result["equity_total"] == "400.00"

    def test_broken_equation_raises(self, builder):
        rows = [
            _row("1101", "Caja", AccountType.ASSET, "1000.00", "0.00"),
            _row("2101", "Proveedores", AccountType.LIABILITY, "0.00", "300.00"),
            # revenue missing → assets != liabilities + equity + income
            _row("5101", "Gastos", AccountType.EXPENSE, "300.00", "0.00"),
        ]
        # rows are individually consistent as a trial balance (1300 dr, 300 cr → unbalanced anyway)
        with pytest.raises(FinanceDomainError):
            builder.balance_sheet(rows)

    def test_contra_revenue_reduces_net_revenue(self, builder):
        rows = [
            _row("1101", "Caja", AccountType.ASSET, "900.00", "0.00"),
            _row("4101", "Ingresos", AccountType.REVENUE, "0.00", "1000.00"),
            _row("4201", "Descuentos sobre venta", AccountType.CONTRA_REVENUE, "100.00", "0.00"),
        ]
        result = builder.income_statement(rows)
        assert result["net_revenue"] == "900.00"
        assert result["net_income"] == "900.00"
