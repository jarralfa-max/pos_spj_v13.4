"""Lo que los módulos operativos aún no entregan al mayor (cierre mensual §9).

Lee, en sólo lectura, los turnos de caja abiertos y los eventos con impacto
financiero que siguen pendientes en el outbox de cada módulo. Los conjuntos de
eventos son los MISMOS que cada módulo suscribe hacia Finanzas (no una lista
paralela que se desincronice).
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.application.finance.ports import OperationalCloseStatus

_OPEN_SHIFT_STATUSES = ("OPENING", "OPEN", "SUSPENDED", "PENDING_COUNT", "COUNTING",
                        "COUNTED", "PENDING_REVIEW", "CLOSING")


def _sales_events() -> frozenset[str]:
    from backend.application.sales.integrations.wiring import REQUIRES_CONSUMER
    return REQUIRES_CONSUMER


def _cash_events() -> frozenset[str]:
    from backend.application.cash_register.finance_wiring import FINANCE_EVENTS
    return FINANCE_EVENTS


def _hr_events() -> frozenset[str]:
    from backend.application.use_cases.hr.finance_wiring import (
        EMPLOYEE_LOAN_GRANTED,
        PAYROLL_PAID,
        PAYROLL_PAYMENT_REVERSED,
    )
    return frozenset({PAYROLL_PAID, EMPLOYEE_LOAN_GRANTED, PAYROLL_PAYMENT_REVERSED})


#: Eventos de Compras que atienden los puentes de Finanzas (event_wiring).
_PROCUREMENT_EVENTS = frozenset({
    "PAYABLE_CREATED", "SUPPLIER_PAYMENT_SCHEDULED", "GOODS_RECEIPT_REVERSED",
    "DIRECT_PURCHASE_REVERSED", "PURCHASE_RETURN_CONFIRMED",
    "PURCHASE_PAYABLE_CREDIT_REQUESTED",
})


class SqliteOperationalCloseSources:
    def __init__(self, connection) -> None:
        self._conn = connection

    def _pending(self, table: str, names: frozenset[str], until: str,
                 pending_statuses: tuple[str, ...] = ("PENDING",),
                 date_column: str = "created_at") -> int:
        if not names:
            return 0
        marks = ",".join("?" for _ in names)
        states = ",".join("?" for _ in pending_statuses)
        row = self._conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE status IN ({states})"
            f" AND event_name IN ({marks}) AND {date_column} < ?",
            (*pending_statuses, *sorted(names), until)).fetchone()
        return int(row[0] or 0)

    def status(self, *, period_start: date, period_end: date) -> OperationalCloseStatus:
        until = (period_end + timedelta(days=1)).isoformat()
        shifts = self._conn.execute(
            "SELECT COUNT(*) FROM cash_shifts WHERE status IN ({})"
            " AND COALESCE(business_date, substr(opened_at, 1, 10)) <= ?".format(
                ",".join("?" for _ in _OPEN_SHIFT_STATUSES)),
            (*_OPEN_SHIFT_STATUSES, period_end.isoformat())).fetchone()
        return OperationalCloseStatus(
            open_cash_shifts=int(shifts[0] or 0),
            pending_sales_events=self._pending("sales_outbox", _sales_events(), until),
            pending_purchase_events=self._pending("procurement_outbox", _PROCUREMENT_EVENTS,
                                                  until),
            pending_payroll_events=self._pending("hr_outbox", _hr_events(), until),
            pending_inventory_events=(
                self._pending("costing_outbox", frozenset({"PROCESSING_COST_ALLOCATED"}), until)
                + self._pending("cash_outbox", _cash_events(), until,
                                pending_statuses=("PENDING", "PROCESSING", "FAILED"))),
        )
