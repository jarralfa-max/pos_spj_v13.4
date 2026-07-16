"""FinancialStatementBuilder — pure computation of financial statements.

Input is a list of account balance rows (already aggregated from POSTED journal
lines by the query layer). No SQL, no repositories here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.finance.enums import AccountType, CashFlowCategory, NormalBalance
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.value_objects.money import Money

_BALANCE_SHEET_TYPES = (AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY)
_INCOME_TYPES = (
    AccountType.REVENUE, AccountType.CONTRA_REVENUE, AccountType.COST_OF_SALES,
    AccountType.EXPENSE, AccountType.OTHER_INCOME, AccountType.OTHER_EXPENSE,
)


@dataclass(frozen=True, slots=True)
class AccountBalanceRow:
    account_id: str
    account_code: str
    account_name: str
    account_type: AccountType
    normal_balance: NormalBalance
    total_debits: Money
    total_credits: Money
    cash_flow_category: CashFlowCategory = CashFlowCategory.NONE

    def natural_balance(self) -> Money:
        """Balance expressed in the account's natural side (positive = normal)."""
        if self.normal_balance is NormalBalance.DEBIT:
            return self.total_debits.subtract(self.total_credits)
        return self.total_credits.subtract(self.total_debits)


@dataclass(frozen=True, slots=True)
class TrialBalanceRow:
    account_id: str
    account_code: str
    account_name: str
    account_type: str
    debit_total: str
    credit_total: str
    balance: str


@dataclass(frozen=True, slots=True)
class StatementSection:
    title: str
    rows: list[tuple[str, str]] = field(default_factory=list)  # (label, amount str)
    total: str = "0"


class FinancialStatementBuilder:
    """Builds trial balance, balance sheet, income statement, cash-flow and
    equity-change structures. Validates the accounting equation."""

    def __init__(self, currency_code: str = "MXN") -> None:
        self._currency = currency_code

    # ── trial balance ─────────────────────────────────────────────────────
    def trial_balance(self, rows: list[AccountBalanceRow]) -> list[TrialBalanceRow]:
        result = [
            TrialBalanceRow(
                account_id=row.account_id,
                account_code=row.account_code,
                account_name=row.account_name,
                account_type=row.account_type.value,
                debit_total=row.total_debits.to_string(),
                credit_total=row.total_credits.to_string(),
                balance=row.natural_balance().to_string(),
            )
            for row in sorted(rows, key=lambda r: r.account_code)
        ]
        self.assert_trial_balance_balanced(rows)
        return result

    def assert_trial_balance_balanced(self, rows: list[AccountBalanceRow]) -> None:
        debits = Money.zero(self._currency)
        credits = Money.zero(self._currency)
        for row in rows:
            debits = debits.add(row.total_debits)
            credits = credits.add(row.total_credits)
        if debits.amount != credits.amount:
            raise FinanceDomainError(
                f"Trial balance is unbalanced: debits={debits.to_string()} credits={credits.to_string()}"
            )

    # ── income statement ──────────────────────────────────────────────────
    def net_income(self, rows: list[AccountBalanceRow]) -> Money:
        revenue = self._sum_types(rows, (AccountType.REVENUE, AccountType.OTHER_INCOME))
        contra = self._sum_types(rows, (AccountType.CONTRA_REVENUE,))
        costs = self._sum_types(rows, (AccountType.COST_OF_SALES,))
        expenses = self._sum_types(rows, (AccountType.EXPENSE, AccountType.OTHER_EXPENSE))
        return revenue.subtract(contra).subtract(costs).subtract(expenses)

    def income_statement(self, rows: list[AccountBalanceRow]) -> dict:
        revenue = self._sum_types(rows, (AccountType.REVENUE,))
        contra = self._sum_types(rows, (AccountType.CONTRA_REVENUE,))
        net_revenue = revenue.subtract(contra)
        cogs = self._sum_types(rows, (AccountType.COST_OF_SALES,))
        gross = net_revenue.subtract(cogs)
        expenses = self._sum_types(rows, (AccountType.EXPENSE,))
        operating = gross.subtract(expenses)
        other_income = self._sum_types(rows, (AccountType.OTHER_INCOME,))
        other_expense = self._sum_types(rows, (AccountType.OTHER_EXPENSE,))
        net = operating.add(other_income).subtract(other_expense)
        return {
            "revenue": revenue.to_string(),
            "contra_revenue": contra.to_string(),
            "net_revenue": net_revenue.to_string(),
            "cost_of_sales": cogs.to_string(),
            "gross_profit": gross.to_string(),
            "operating_expenses": expenses.to_string(),
            "operating_income": operating.to_string(),
            "other_income": other_income.to_string(),
            "other_expense": other_expense.to_string(),
            "net_income": net.to_string(),
            "sections": self._detail_sections(rows, _INCOME_TYPES),
        }

    # ── balance sheet ─────────────────────────────────────────────────────
    def balance_sheet(self, rows: list[AccountBalanceRow]) -> dict:
        assets = self._sum_types(rows, (AccountType.ASSET,))
        liabilities = self._sum_types(rows, (AccountType.LIABILITY,))
        equity = self._sum_types(rows, (AccountType.EQUITY,))
        net = self.net_income(rows)
        equity_total = equity.add(net)
        self.assert_accounting_equation(rows)
        return {
            "assets": assets.to_string(),
            "liabilities": liabilities.to_string(),
            "equity": equity.to_string(),
            "period_net_income": net.to_string(),
            "equity_total": equity_total.to_string(),
            "sections": self._detail_sections(rows, _BALANCE_SHEET_TYPES),
        }

    def assert_accounting_equation(self, rows: list[AccountBalanceRow]) -> None:
        assets = self._sum_types(rows, (AccountType.ASSET,))
        liabilities = self._sum_types(rows, (AccountType.LIABILITY,))
        equity = self._sum_types(rows, (AccountType.EQUITY,)).add(self.net_income(rows))
        if assets.amount != liabilities.add(equity).amount:
            raise FinanceDomainError(
                f"Accounting equation violated: assets={assets.to_string()} != "
                f"liabilities+equity={liabilities.add(equity).to_string()}"
            )

    # ── cash flow (indirect by category) ──────────────────────────────────
    def cash_flow_statement(self, rows: list[AccountBalanceRow]) -> dict:
        flows = {
            CashFlowCategory.OPERATING: Money.zero(self._currency),
            CashFlowCategory.INVESTING: Money.zero(self._currency),
            CashFlowCategory.FINANCING: Money.zero(self._currency),
        }
        for row in rows:
            if row.cash_flow_category in flows:
                # Inflow positive when the movement increases cash: for DEBIT-natured
                # cash mirrors the natural balance; other accounts contribute inversely.
                delta = row.natural_balance()
                if row.account_type is AccountType.ASSET and row.cash_flow_category is not CashFlowCategory.OPERATING:
                    delta = delta.negate()
                flows[row.cash_flow_category] = flows[row.cash_flow_category].add(delta)
        net = (flows[CashFlowCategory.OPERATING]
               .add(flows[CashFlowCategory.INVESTING])
               .add(flows[CashFlowCategory.FINANCING]))
        return {
            "operating": flows[CashFlowCategory.OPERATING].to_string(),
            "investing": flows[CashFlowCategory.INVESTING].to_string(),
            "financing": flows[CashFlowCategory.FINANCING].to_string(),
            "net_change_in_cash": net.to_string(),
        }

    # ── equity changes ────────────────────────────────────────────────────
    def equity_changes(self, opening_rows: list[AccountBalanceRow],
                       closing_rows: list[AccountBalanceRow]) -> dict:
        opening = self._sum_types(opening_rows, (AccountType.EQUITY,)).add(self.net_income(opening_rows))
        closing = self._sum_types(closing_rows, (AccountType.EQUITY,)).add(self.net_income(closing_rows))
        return {
            "opening_equity": opening.to_string(),
            "closing_equity": closing.to_string(),
            "change": closing.subtract(opening).to_string(),
        }

    # ── helpers ───────────────────────────────────────────────────────────
    def _sum_types(self, rows: list[AccountBalanceRow], types: tuple[AccountType, ...]) -> Money:
        total = Money.zero(self._currency)
        for row in rows:
            if row.account_type in types:
                total = total.add(row.natural_balance())
        return total

    def _detail_sections(self, rows: list[AccountBalanceRow],
                         types: tuple[AccountType, ...]) -> list[dict]:
        sections: list[dict] = []
        for account_type in types:
            type_rows = sorted(
                (r for r in rows if r.account_type is account_type),
                key=lambda r: r.account_code,
            )
            if not type_rows:
                continue
            total = self._sum_types(type_rows, (account_type,))
            sections.append({
                "account_type": account_type.value,
                "rows": [
                    {"code": r.account_code, "name": r.account_name,
                     "balance": r.natural_balance().to_string()}
                    for r in type_rows
                ],
                "total": total.to_string(),
            })
        return sections
