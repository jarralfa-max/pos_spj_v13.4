"""CashProjectionQueryService — proyección de efectivo de corto plazo (§32).

Modelo de PLANEACIÓN separado de la contabilidad: sólo lee, nunca asienta.
Parte del efectivo contable de hoy y suma por semana:

- entradas: vencimientos de CxC abiertas (las vencidas se esperan la primera semana);
- salidas: vencimientos de CxP abiertas, pagos ya programados, gastos aprobados
  aún sin devengar (incluye CAPEX aprobado), planes de gasto recurrente y la
  nómina prevista (promedio mensual de la nómina contabilizada de los últimos
  meses, rotulada como estimación).

No confunde utilidad con efectivo: no usa ingresos ni gastos devengados.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from backend.application.queries.finance.base_finance_query_service import (
    POSTED,
    FinanceQueryServiceBase,
    decimal_sum,
    money_text,
)
from backend.application.queries.finance.general_ledger_query_service import (
    GeneralLedgerQueryService,
)
from backend.domain.finance.enums import OPEN_PAYABLE_STATUSES, OPEN_RECEIVABLE_STATUSES, sql_in

_STEP = {"WEEKLY": 7, "BIWEEKLY": 14}


def _advance(current: date, frequency: str) -> date:
    if frequency in _STEP:
        return current + timedelta(days=_STEP[frequency])
    months = {"MONTHLY": 1, "QUARTERLY": 3, "YEARLY": 12}[frequency]
    month = current.month - 1 + months
    year = current.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(current.day, calendar.monthrange(year, month)[1]))


class CashProjectionQueryService(FinanceQueryServiceBase):
    def projection(self, *, as_of: str, weeks: int, payroll_months: int) -> dict:
        """``weeks``: horizonte; ``payroll_months``: meses de historia para estimar
        la nómina. Ambos los decide quien consulta (configuración), nunca la UI."""
        if weeks <= 0:
            raise ValueError("El horizonte debe ser de al menos una semana")
        start = date.fromisoformat(as_of)
        end = start + timedelta(days=7 * weeks - 1)
        ledger = GeneralLedgerQueryService(self._conn)
        opening = ledger.cash_balance(ledger.cash_account_ids(), until=as_of)
        buckets = [{"week_start": (start + timedelta(days=7 * i)).isoformat(),
                    "inflows": Decimal("0"), "outflows": Decimal("0")} for i in range(weeks)]

        def put(on: date, amount: Decimal, kind: str) -> None:
            index = max(0, (on - start).days // 7)
            if index < weeks:
                buckets[index][kind] += amount

        for row in self._query(
                f"SELECT outstanding_amount, due_date FROM receivables WHERE status IN"
                f" {sql_in(OPEN_RECEIVABLE_STATUSES)} AND status <> 'DISPUTED'"
                " AND due_date IS NOT NULL AND due_date <= ?", (end.isoformat(),)):
            put(date.fromisoformat(row["due_date"][:10]),
                decimal_sum([row["outstanding_amount"]]), "inflows")
        scheduled = {r["payable_id"]: r for r in self._query(
            "SELECT payable_id, scheduled_date, amount FROM supplier_payments"
            " WHERE status IN ('SCHEDULED','AUTHORIZED')")}
        for row in self._query(
                f"SELECT id, outstanding_amount, due_date FROM payables WHERE status IN"
                f" {sql_in(OPEN_PAYABLE_STATUSES)} AND due_date IS NOT NULL AND due_date <= ?",
                (end.isoformat(),)):
            payment = scheduled.pop(row["id"], None)
            when = payment["scheduled_date"] if payment else row["due_date"]
            put(date.fromisoformat(when[:10]), decimal_sum([row["outstanding_amount"]]),
                "outflows")
        for payment in scheduled.values():
            put(date.fromisoformat(payment["scheduled_date"][:10]),
                decimal_sum([payment["amount"]]), "outflows")
        for row in self._query("SELECT amount, period_code FROM expense_requests"
                               " WHERE status='APPROVED'"):
            put(start, decimal_sum([row["amount"]]), "outflows")
        for plan in self._query("SELECT amount, frequency, next_date FROM"
                                " recurring_expense_plans WHERE active=1"):
            on = date.fromisoformat(plan["next_date"][:10])
            while on <= end:
                if on >= start:
                    put(on, decimal_sum([plan["amount"]]), "outflows")
                on = _advance(on, plan["frequency"])
        payroll = self._monthly_payroll(start, payroll_months)
        if payroll:
            month_cursor = date(start.year, start.month, 1)
            while month_cursor <= end:
                pay_day = month_cursor + timedelta(days=27)
                if start <= pay_day <= end:
                    put(pay_day, payroll, "outflows")
                month_cursor = _advance(month_cursor, "MONTHLY")
        balance = opening
        rows = []
        for bucket in buckets:
            net = bucket["inflows"] - bucket["outflows"]
            balance += net
            rows.append({"week_start": bucket["week_start"],
                         "inflows": money_text(bucket["inflows"]),
                         "outflows": money_text(bucket["outflows"]),
                         "net": money_text(net), "closing_balance": money_text(balance)})
        return {"as_of": as_of, "opening_balance": money_text(opening), "weeks": rows,
                "estimated_monthly_payroll": money_text(payroll),
                "is_estimate": True}

    def _monthly_payroll(self, start: date, months: int) -> Decimal:
        if months <= 0:
            return Decimal("0")
        since = start - timedelta(days=31 * months)
        rows = self._query(
            "SELECT jl.base_credit_amount FROM journal_lines jl JOIN journal_entries je"
            " ON je.id = jl.journal_entry_id WHERE je.posting_purpose = 'PAYROLL'"
            f" AND je.status IN {POSTED} AND je.posting_date >= ? AND jl.base_credit_amount <> '0.00'"
            " AND jl.account_id IN (SELECT ledger_account_id FROM treasury_accounts)",
            (since.isoformat(),))
        total = decimal_sum(r["base_credit_amount"] for r in rows)
        return (total / months).quantize(Decimal("0.01"))
