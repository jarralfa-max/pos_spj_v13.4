"""OpenFiscalPeriodUseCase — abre un periodo contable mensual (idempotente)."""

from __future__ import annotations

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.enums import AuditAction
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


class OpenFiscalPeriodUseCase:
    def execute(self, connection, year: int, month: int, *, operation_id: str,
                opened_by: str | None = None) -> FiscalPeriod:
        with FinanceUnitOfWork(connection) as uow:
            existing = uow.fiscal_periods.find_by_code(year, month)
            if existing is not None:
                return existing
            period = FiscalPeriod.open_for(year, month)
            uow.fiscal_periods.save(period)
            uow.audit(AuditAction.PERIOD_OPENED, entity_type="fiscal_period",
                      entity_id=period.id, operation_id=operation_id, user_id=opened_by,
                      after={"period": period.period.code(), "status": period.status.value})
            publish_finance_event(uow, EventName.FISCAL_PERIOD_OPENED, {
                "fiscal_period_id": period.id, "period": period.period.code(),
                "status": period.status.value, "actor": opened_by,
            }, operation_id=operation_id, entity_id=period.id)
            return period
