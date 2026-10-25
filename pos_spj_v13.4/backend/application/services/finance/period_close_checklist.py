"""Checklist del cierre mensual (§9).

Cada punto se MIDE (no se marca a mano) y tiene estado:

- OK: cumplido;
- BLOCKING: impide cerrar (caja abierta, eventos sin contabilizar, conciliación
  abierta, depreciación pendiente, asiento descuadrado, borradores del periodo,
  diferencia material sin autorizar);
- WARNING: se informa y no bloquea (eventos financieros propios que no se han
  entregado a otros módulos, CxC/CxP vencidas sin gestionar).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from backend.application.finance.ports import OperationalCloseSourcesPort
from backend.application.services.finance.close_controls import (
    CHECK_PAYABLES,
    CHECK_RECEIVABLES,
    FinanceCloseControls,
)
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork

OK, BLOCKING, WARNING = "OK", "BLOCKING", "WARNING"


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    key: str
    label: str
    status: str
    detail: str = ""


def _item(key: str, label: str, count: int, detail: str, *,
          severity: str = BLOCKING) -> ChecklistItem:
    return ChecklistItem(key, label, OK if count == 0 else severity,
                         "" if count == 0 else detail)


class PeriodCloseChecklist:
    def __init__(self, operational_sources: OperationalCloseSourcesPort) -> None:
        self._sources = operational_sources

    def evaluate(self, connection, *, year: int, month: int) -> list[ChecklistItem]:
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        code = f"{year:04d}-{month:02d}"
        with FinanceUnitOfWork(connection) as uow:
            materiality = uow.settings.close_materiality_threshold
        exceptions = FinanceCloseControls(str(materiality)).run(
            connection, period_code=code, as_of=end)
        status = self._sources.status(period_start=start, period_end=end)
        with FinanceUnitOfWork(connection) as uow:
            open_recs = uow.reconciliations.list_open(statement_date_until=end.isoformat())
            unposted = uow.journal_entries.count_unposted(date_from=start.isoformat(),
                                                          date_to=end.isoformat())
            depreciation_due = self._assets_pending_depreciation(uow, code, end)
            unbalanced = uow.journal_entries.exists_unbalanced()
            failing_outbox = uow.outbox.count_failing()
            overdue_receivables = len(uow.receivables.list_overdue_candidates(end))
            overdue_payables = len(uow.payables.list_overdue_candidates(end))
        subledger = {CHECK_RECEIVABLES: 0, CHECK_PAYABLES: 0}
        others = 0
        for exception in exceptions:
            if exception["check_type"] in subledger:
                subledger[exception["check_type"]] += 1
            else:
                others += 1
        return [
            _item("cash_shifts_closed", "Cajas cerradas", status.open_cash_shifts,
                  f"{status.open_cash_shifts} turnos de caja siguen abiertos"),
            _item("sales_posted", "Ventas contabilizadas", status.pending_sales_events,
                  f"{status.pending_sales_events} eventos de venta sin llegar al mayor"),
            _item("purchases_posted", "Compras contabilizadas", status.pending_purchase_events,
                  f"{status.pending_purchase_events} eventos de compra sin llegar al mayor"),
            _item("payroll_posted", "Nómina contabilizada", status.pending_payroll_events,
                  f"{status.pending_payroll_events} pagos de nómina sin llegar al mayor"),
            _item("inventory_valued", "Inventario valorizado", status.pending_inventory_events,
                  f"{status.pending_inventory_events} movimientos con costo sin contabilizar"),
            _item("reconciliations_completed", "Conciliaciones completadas", len(open_recs),
                  f"{len(open_recs)} conciliaciones abiertas con estados del periodo"),
            _item("depreciation_run", "Depreciaciones calculadas", depreciation_due,
                  f"{depreciation_due} activos sin depreciación de {code}"),
            _item("receivables_reviewed", "CxC revisadas", subledger[CHECK_RECEIVABLES],
                  "El auxiliar de CxC no cuadra con el mayor"),
            _item("receivables_overdue", "CxC vencidas gestionadas", overdue_receivables,
                  f"{overdue_receivables} CxC vencidas sin marcar", severity=WARNING),
            _item("payables_reviewed", "CxP revisadas", subledger[CHECK_PAYABLES],
                  "El auxiliar de CxP no cuadra con el mayor"),
            _item("payables_overdue", "CxP vencidas gestionadas", overdue_payables,
                  f"{overdue_payables} CxP vencidas sin marcar", severity=WARNING),
            _item("no_unbalanced_entries", "Sin asientos desbalanceados", int(unbalanced),
                  "Existen asientos descuadrados en el mayor"),
            _item("pending_documents", "Sin documentos pendientes", unposted,
                  f"{unposted} asientos manuales del periodo sin contabilizar o cancelar"),
            _item("material_differences", "Diferencias materiales resueltas", others,
                  f"{others} diferencias materiales sin resolver ni autorizar"),
            _item("finance_events_delivered", "Eventos financieros entregados", failing_outbox,
                  f"{failing_outbox} eventos financieros con reintentos fallidos",
                  severity=WARNING),
        ]

    @staticmethod
    def _assets_pending_depreciation(uow: FinanceUnitOfWork, period: str, end: date) -> int:
        depreciated = {row["fixed_asset_id"] for row in uow.fixed_assets.run_lines(period)}
        pending = 0
        for asset in uow.fixed_assets.list_capitalized():
            if asset.capitalization_date is None or asset.capitalization_date > end:
                continue
            if asset.is_fully_depreciated or asset.id in depreciated:
                continue
            if asset.last_depreciated_period is not None and asset.last_depreciated_period >= period:
                continue
            pending += 1
        return pending


def blocking_items(items: list[ChecklistItem]) -> list[ChecklistItem]:
    return [item for item in items if item.status == BLOCKING]
