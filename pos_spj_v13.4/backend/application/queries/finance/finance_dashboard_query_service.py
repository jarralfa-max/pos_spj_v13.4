"""FinanceDashboardQueryService — tablero financiero (§29, §30).

Todo se calcula aquí, desde el mayor y los auxiliares: 12 KPI, 8 alertas y 10
gráficas como ``ChartDataDTO`` para ``HtmlChartView`` (ECharts). La pantalla no
calcula nada. Horizontes (meses de tendencia, días de pagos próximos) vienen de
la configuración de Finanzas.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.application.dto.charts.chart_data import ChartDataDTO, ChartType, series_from
from backend.application.dto.finance.finance_dashboard_dto import (
    FinanceAlertDTO,
    FinanceDashboardDTO,
    FinanceKpiDTO,
)
from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
    LedgerFilter,
    decimal_sum,
    money_text,
)
from backend.application.queries.finance.budget_query_service import BudgetQueryService
from backend.application.queries.finance.finance_settings_query_service import (
    FinanceSettingsQueryService,
)
from backend.application.queries.finance.financial_statement_query_service import (
    FinancialStatementQueryService,
)
from backend.application.queries.finance.general_ledger_query_service import (
    GeneralLedgerQueryService,
)
from backend.application.queries.finance.payable_query_service import PayableQueryService
from backend.application.queries.finance.profitability_query_service import (
    ProfitabilityQueryService,
)
from backend.application.queries.finance.receivable_query_service import ReceivableQueryService
from backend.application.queries.finance.treasury_query_service import TreasuryQueryService
from backend.domain.finance.enums import (
    OPEN_PAYABLE_STATUSES,
    OPEN_RECEIVABLE_STATUSES,
    AccountType,
    CashFlowCategory,
    sql_in,
)

_AGING_LABEL = {"CURRENT": "Por vencer", "1-30": "1-30 días", "31-60": "31-60 días",
                "61-90": "61-90 días", "90+": "Más de 90", "NO_DUE_DATE": "Sin vencimiento"}


class _NoNames:
    def display_names(self, ids):
        return {}

    def search(self, text, limit=20):
        return []

    def category_names(self, ids):
        return {}


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    return (date(year, month, 1).isoformat(),
            date(year, month, calendar.monthrange(year, month)[1]).isoformat())


def _previous_months(today: date, count: int) -> list[tuple[int, int]]:
    months, year, month = [], today.year, today.month
    for _ in range(max(count, 1)):
        months.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


def _f(value) -> float:
    """Sólo para el DTO de gráfica (presentación); los cálculos son Decimal."""
    return float(Decimal(str(value)))


class FinanceDashboardQueryService(FinanceQueryServiceBase):
    def __init__(self, connection, *, products=None) -> None:
        super().__init__(connection)
        self._ledger = GeneralLedgerQueryService(connection)
        self._statements = FinancialStatementQueryService(connection)
        self._treasury = TreasuryQueryService(connection)
        self._receivables = ReceivableQueryService(connection, _NoNames())
        self._payables = PayableQueryService(connection, _NoNames())
        self._budgets = BudgetQueryService(connection)
        self._profitability = ProfitabilityQueryService(connection, products=products)
        self._settings = FinanceSettingsQueryService(connection)

    # ── tablero ──────────────────────────────────────────────────────────
    def dashboard(self, *, today: date | None = None, with_charts: bool = True
                  ) -> FinanceDashboardDTO:
        today = today or date.today()
        settings = self._settings.settings()
        month_from, month_to = date(today.year, today.month, 1).isoformat(), today.isoformat()
        income = self._statements.income_statement(date_from=month_from, date_to=month_to)
        cash_flow = self._statements.cash_flow_statement(date_from=month_from, date_to=month_to)
        position = self._treasury.treasury_position()
        currency = self._ledger.base_currency()
        cash = decimal_sum(a["available"] for a in self._unique_mirrors(position)
                           if a["account_type"] in ("GENERAL_CASH", "PETTY_CASH",
                                                    "CASH_REGISTER"))
        bank = decimal_sum(a["balance"] for a in self._unique_mirrors(position)
                           if a["account_type"] == "BANK")
        receivables = self._money_sum(f"SELECT outstanding_amount FROM receivables"
                                      f" WHERE status IN {sql_in(OPEN_RECEIVABLE_STATUSES)}")
        overdue = self._money_sum(
            f"SELECT outstanding_amount FROM receivables WHERE status IN"
            f" {sql_in(OPEN_RECEIVABLE_STATUSES)} AND due_date IS NOT NULL AND due_date < ?",
            (today.isoformat(),))
        payables = self._money_sum(f"SELECT outstanding_amount FROM payables"
                                   f" WHERE status IN {sql_in(OPEN_PAYABLE_STATUSES)}")
        upcoming = money_text(decimal_sum(
            r["outstanding_amount"] for r in self._payables.upcoming_payments(
                as_of=today.isoformat(), days=settings.upcoming_payments_days)))
        execution = self._budgets.budget_execution(today.year)
        budget_available = money_text(decimal_sum(r["available"] for r in execution))
        gross_margin = Decimal(income["gross_profit"])
        net_revenue = Decimal(income["net_revenue"])
        kpis = (
            FinanceKpiDTO("cash_available", "Efectivo disponible", money_text(cash)),
            FinanceKpiDTO("bank_balance", "Saldo bancario", money_text(bank)),
            FinanceKpiDTO("receivables", "Cuentas por cobrar", receivables),
            FinanceKpiDTO("receivables_overdue", "CxC vencidas", overdue,
                          "danger" if Decimal(overdue) > 0 else "success"),
            FinanceKpiDTO("payables", "Cuentas por pagar", payables),
            FinanceKpiDTO("upcoming_payments", "Pagos próximos", upcoming, "warning",
                          hint=f"{settings.upcoming_payments_days} días"),
            FinanceKpiDTO("net_sales", "Ventas netas del mes", income["net_revenue"], "success"),
            FinanceKpiDTO("gross_margin", "Margen bruto", money_text(gross_margin),
                          "success" if gross_margin >= 0 else "danger",
                          hint=(f"{(gross_margin * 100 / net_revenue).quantize(Decimal('0.1'))} %"
                                if net_revenue else "")),
            FinanceKpiDTO("operating_expenses", "Gastos operativos", income["operating_expenses"],
                          "warning"),
            FinanceKpiDTO("operating_income", "Utilidad operativa", income["operating_income"],
                          "success" if Decimal(income["operating_income"]) >= 0 else "danger"),
            FinanceKpiDTO("net_cash_flow", "Flujo neto del mes",
                          str(cash_flow.get("net_change_in_cash", "0.00")),
                          "success" if Decimal(str(cash_flow.get("net_change_in_cash", "0")))
                          >= 0 else "danger"),
            FinanceKpiDTO("budget_available", "Presupuesto disponible", budget_available),
        )
        return FinanceDashboardDTO(
            period_from=month_from, period_to=month_to, currency_code=currency, kpis=kpis,
            alerts=self.alerts(today=today, execution=execution),
            charts=self.charts(today=today, months=settings.dashboard_trend_months)
            if with_charts else ())

    @staticmethod
    def _unique_mirrors(position: list[dict]) -> list[dict]:
        seen, result = set(), []
        for account in position:
            if account["ledger_account_id"] in seen:
                continue
            seen.add(account["ledger_account_id"])
            result.append(account)
        return result

    # ── alertas ──────────────────────────────────────────────────────────
    def alerts(self, *, today: date, execution: list[dict] | None = None
               ) -> tuple[FinanceAlertDTO, ...]:
        execution = execution if execution is not None else \
            self._budgets.budget_execution(today.year)
        current = (today.year, today.month)
        pending_close = sum(1 for p in self._query(
            "SELECT year, month, status FROM fiscal_periods WHERE status <> 'CLOSED'")
            if (p["year"], p["month"]) < current)
        drafts = int(self._scalar("SELECT COUNT(*) FROM journal_entries"
                                  " WHERE status IN ('DRAFT','VALIDATED')"))
        reconciliations = int(self._scalar("SELECT COUNT(*) FROM reconciliations"
                                           " WHERE status IN ('OPEN','IN_PROGRESS')")) + len(
            self._query("SELECT id FROM bank_statements WHERE id NOT IN"
                        " (SELECT bank_statement_id FROM reconciliations"
                        "  WHERE status <> 'REVERTED')"))
        difference_accounts = sorted(self._statements.profile_accounts(
            "CASH_SHIFT", ("cash_over_account_id", "cash_short_account_id")))
        cash_differences = 0
        if difference_accounts:
            marks = ",".join("?" for _ in difference_accounts)
            cash_differences = int(self._scalar(
                "SELECT COUNT(DISTINCT je.id) FROM journal_entries je JOIN journal_lines jl"
                " ON jl.journal_entry_id = je.id WHERE je.posting_purpose='CASH_SHIFT_CLOSE'"
                f" AND je.status='POSTED' AND je.posting_date >= ? AND jl.account_id IN ({marks})",
                (date(today.year, today.month, 1).isoformat(), *difference_accounts)))
        overdue_receivables = int(self._scalar(
            f"SELECT COUNT(*) FROM receivables WHERE status IN {sql_in(OPEN_RECEIVABLE_STATUSES)}"
            " AND due_date IS NOT NULL AND due_date < ?", (today.isoformat(),)))
        overdue_payables = int(self._scalar(
            f"SELECT COUNT(*) FROM payables WHERE status IN {sql_in(OPEN_PAYABLE_STATUSES)}"
            " AND due_date IS NOT NULL AND due_date < ?", (today.isoformat(),)))
        exceeded = sum(1 for r in execution if r["control_level"] == "BLOCKING")
        awaiting = int(self._scalar("SELECT COUNT(*) FROM supplier_payments"
                                    " WHERE status='SCHEDULED'"))
        candidates = (
            FinanceAlertDTO("periods_pending_close", "Periodos pendientes de cierre",
                            pending_close, "warning", "periods"),
            FinanceAlertDTO("draft_entries", "Asientos en borrador", drafts, "info", "journal"),
            FinanceAlertDTO("pending_reconciliations", "Conciliaciones pendientes",
                            reconciliations, "warning", "reconciliation"),
            FinanceAlertDTO("cash_differences", "Cortes con diferencia de caja este mes",
                            cash_differences, "warning", "treasury"),
            FinanceAlertDTO("overdue_receivables", "CxC vencidas", overdue_receivables,
                            "danger", "receivables"),
            FinanceAlertDTO("overdue_payables", "CxP vencidas", overdue_payables, "danger",
                            "payables"),
            FinanceAlertDTO("budgets_exceeded", "Partidas presupuestales excedidas", exceeded,
                            "danger", "budgets"),
            FinanceAlertDTO("payments_awaiting_authorization", "Pagos esperando autorización",
                            awaiting, "warning", "payments"),
        )
        return tuple(a for a in candidates if a.count > 0)

    # ── gráficas (§30) ───────────────────────────────────────────────────
    def charts(self, *, today: date, months: int) -> tuple[ChartDataDTO, ...]:
        now = datetime.now(timezone.utc)
        periods = _previous_months(today, months)
        labels = tuple(f"{year}-{month:02d}" for year, month in periods)
        revenue, costs, expenses, net, cash_net, working = [], [], [], [], [], []
        for year, month in periods:
            start, end = _month_bounds(year, month)
            statement = self._statements.income_statement(date_from=start, date_to=end)
            revenue.append(_f(statement["net_revenue"]))
            costs.append(_f(statement["cost_of_sales"]))
            expenses.append(_f(statement["operating_expenses"]))
            net.append(_f(statement["net_income"]))
            flow = self._statements.cash_flow_statement(date_from=start, date_to=end)
            cash_net.append(_f(flow.get("net_change_in_cash", "0")))
            working.append(_f(self._working_capital(end)))
        currency = self._ledger.base_currency()
        common = dict(currency_code=currency, generated_at=now)

        def chart(chart_id, chart_type, title, categories, series, **extra):
            dto = ChartDataDTO(chart_id=chart_id, chart_type=chart_type, title=title,
                               subtitle=None, categories=tuple(categories),
                               series=tuple(series), **common, **extra)
            return dto if not dto.is_empty() else ChartDataDTO.empty(chart_id, chart_type, title)

        rec_aging = self._receivables.aging_summary(today.isoformat())
        pay_aging = self._payables.aging(today.isoformat())
        budget = self._budgets.budget_vs_actual(today.year)
        position = self._unique_mirrors(self._treasury.treasury_position())
        month_start = date(today.year, today.month, 1).isoformat()
        branches = self._profitability.branch_results(date_from=month_start,
                                                      date_to=today.isoformat())
        categories = self._profitability.by_dimension("category", date_from=month_start,
                                                      date_to=today.isoformat(), limit=10)
        return (
            chart("finance.cash_flow", ChartType.BAR, "Flujo de efectivo por periodo", labels,
                  [series_from("Flujo neto", cash_net)]),
            chart("finance.revenue_costs_expenses", ChartType.BAR,
                  "Ingresos vs costos vs gastos", labels,
                  [series_from("Ingresos netos", revenue, semantic="success"),
                   series_from("Costo de ventas", costs, semantic="warning"),
                   series_from("Gastos operativos", expenses, semantic="danger")]),
            chart("finance.branch_margin", ChartType.BAR, "Margen bruto por sucursal (mes)",
                  [b["branch_id"][-6:] for b in branches],
                  [series_from("Margen bruto", [_f(b["gross_profit"]) for b in branches])]),
            chart("finance.receivable_aging", ChartType.BAR, "Antigüedad de CxC",
                  [_AGING_LABEL[r["bucket"]] for r in rec_aging],
                  [series_from("Saldo", [_f(r["amount"]) for r in rec_aging])]),
            chart("finance.payable_aging", ChartType.BAR, "Antigüedad de CxP",
                  [_AGING_LABEL[r["bucket"]] for r in pay_aging],
                  [series_from("Saldo", [_f(r["amount"]) for r in pay_aging])]),
            chart("finance.budget_vs_actual", ChartType.BAR, "Presupuesto vs real",
                  [r["period_code"] for r in budget],
                  [series_from("Presupuesto", [_f(r["planned"]) for r in budget]),
                   series_from("Real", [_f(r["actual"]) for r in budget])]),
            chart("finance.treasury_balances", ChartType.HORIZONTAL_BAR,
                  "Saldo de tesorería por cuenta", [a["name"] for a in position],
                  [series_from("Saldo", [_f(a["balance"]) for a in position])]),
            chart("finance.category_profitability", ChartType.HORIZONTAL_BAR,
                  "Rentabilidad por categoría (mes)", [c["name"] or "Sin categoría"
                                                       for c in categories],
                  [series_from("Margen de contribución",
                               [_f(c["contribution_margin"]) for c in categories])]),
            chart("finance.profit_trend", ChartType.LINE, "Tendencia de utilidad", labels,
                  [series_from("Resultado neto", net)]),
            chart("finance.working_capital", ChartType.LINE, "Capital de trabajo", labels,
                  [series_from("Capital de trabajo operativo", working)]),
        )

    def _working_capital(self, as_of: str) -> Decimal:
        """Activos operativos menos pasivos operativos (categoría de flujo OPERATIVA
        de la cuenta, configurable en el plan de cuentas)."""
        total = Decimal("0")
        for row in self._ledger.account_balances(LedgerFilter(date_to=as_of)):
            if row.cash_flow_category is not CashFlowCategory.OPERATING:
                continue
            if row.account_type is AccountType.ASSET:
                total += row.natural_balance().amount
            elif row.account_type is AccountType.LIABILITY:
                total -= row.natural_balance().amount
        return total
