"""CloseFiscalPeriodUseCase — pre-cierre o cierre mensual con checklist medido (§9).

Cualquier punto BLOQUEANTE del checklist (caja abierta, eventos operativos sin
contabilizar, conciliación abierta, depreciación pendiente, asiento
descuadrado, borradores del periodo, diferencia material sin autorizar)
impide el cierre; el mensaje enumera qué falta. La evidencia de las
diferencias materiales queda persistida aunque el cierre se rechace.
"""

from __future__ import annotations

from backend.application.finance.ports import OperationalCloseSourcesPort
from backend.application.services.finance.period_close_checklist import (
    PeriodCloseChecklist,
    blocking_items,
)
from backend.application.services.finance.posting_engine import publish_finance_event
from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import MaterialDifferenceError, PeriodNotFoundError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


class CloseFiscalPeriodUseCase:
    def __init__(self, operational_sources: OperationalCloseSourcesPort) -> None:
        self._checklist = PeriodCloseChecklist(operational_sources)

    def checklist(self, connection, year: int, month: int):
        return self._checklist.evaluate(connection, year=year, month=month)

    def execute(self, connection, year: int, month: int, *, closed_by: str,
                operation_id: str, soft: bool = False) -> FiscalPeriod:
        items = self._checklist.evaluate(connection, year=year, month=month)
        blocking = blocking_items(items)
        with FinanceUnitOfWork(connection) as uow:
            period = uow.fiscal_periods.find_by_code(year, month)
            if period is None:
                raise PeriodNotFoundError(f"El periodo {year:04d}-{month:02d} no existe")
            if blocking:
                raise MaterialDifferenceError(
                    "Cierre bloqueado: " + "; ".join(
                        f"{item.label}: {item.detail}" for item in blocking))
            before = {"status": period.status.value}
            if soft:
                period.soft_close(closed_by)
                event = EventName.FISCAL_PERIOD_SOFT_CLOSED
            else:
                period.close(closed_by)
                event = EventName.FISCAL_PERIOD_CLOSED
            uow.fiscal_periods.update(period)
            uow.audit(AuditAction.PERIOD_CLOSED, entity_type="fiscal_period",
                      entity_id=period.id, operation_id=operation_id, user_id=closed_by,
                      before=before,
                      after={"status": period.status.value,
                             "checklist": {item.key: item.status for item in items}})
            publish_finance_event(uow, event, {
                "fiscal_period_id": period.id, "period": period.period.code(),
                "status": period.status.value, "actor": closed_by,
            }, operation_id=operation_id, entity_id=period.id)
            return period
