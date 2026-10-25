"""ReopenFiscalPeriodUseCase — reapertura controlada (§9): permiso especial
(lo exige la capa de comandos), motivo obligatorio, auditoría y evento, con el
usuario y la fecha de la reapertura."""

from __future__ import annotations

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import PeriodNotFoundError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


class ReopenFiscalPeriodUseCase:
    def execute(self, connection, year: int, month: int, *, reason: str,
                operation_id: str, reopened_by: str | None = None) -> FiscalPeriod:
        with FinanceUnitOfWork(connection) as uow:
            period = uow.fiscal_periods.find_by_code(year, month)
            if period is None:
                raise PeriodNotFoundError(f"El periodo {year:04d}-{month:02d} no existe")
            before = {"status": period.status.value, "closed_by": period.closed_by}
            period.reopen(reason, reopened_by)
            uow.fiscal_periods.update(period)
            uow.audit(AuditAction.PERIOD_REOPENED, entity_type="fiscal_period",
                      entity_id=period.id, operation_id=operation_id, user_id=reopened_by,
                      before=before, after={"status": period.status.value}, reason=reason)
            publish_finance_event(uow, EventName.FISCAL_PERIOD_REOPENED, {
                "fiscal_period_id": period.id, "period": period.period.code(),
                "status": period.status.value, "actor": reopened_by, "reason": reason,
            }, operation_id=operation_id, entity_id=period.id)
            return period
