"""Fiscal period use cases — open, soft-close, close and controlled reopen.

Monthly close validation: no unbalanced entries may exist, no open
reconciliations, and commercial instruments must reconcile against the ledger
(material differences block the close).
"""

from __future__ import annotations

import json
import logging

from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    MaterialDifferenceError,
)
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.finance.periods")


def _publish(uow: FinanceUnitOfWork, event_name: EventName, period: FiscalPeriod,
             operation_id: str) -> None:
    uow.outbox.enqueue(
        event_id=new_uuid(),
        event_name=event_name.value,
        payload_json=json.dumps({
            "fiscal_period_id": period.id,
            "period": period.period.code(),
            "status": period.status.value,
        }),
        operation_id=operation_id,
    )


class OpenFiscalPeriodUseCase:
    def execute(self, connection, year: int, month: int, *, operation_id: str) -> FiscalPeriod:
        with FinanceUnitOfWork(connection) as uow:
            existing = uow.fiscal_periods.find_by_code(year, month)
            if existing is not None:
                return existing
            period = FiscalPeriod.open_for(year, month)
            uow.fiscal_periods.save(period)
            _publish(uow, EventName.FISCAL_PERIOD_OPENED, period, operation_id)
            return period


class CloseFiscalPeriodUseCase:
    """Validates the close checklist before closing the month."""

    def execute(self, connection, year: int, month: int, *, closed_by: str,
                operation_id: str, soft: bool = False) -> FiscalPeriod:
        with FinanceUnitOfWork(connection) as uow:
            period = uow.fiscal_periods.find_by_code(year, month)
            if period is None:
                raise FinanceDomainError(f"Fiscal period {year:04d}-{month:02d} does not exist")
            self._validate_close(uow)
            if soft:
                period.soft_close()
                event = EventName.FISCAL_PERIOD_SOFT_CLOSED
            else:
                period.close(closed_by)
                event = EventName.FISCAL_PERIOD_CLOSED
            uow.fiscal_periods.update(period)
            _publish(uow, event, period, operation_id)
            return period

    @staticmethod
    def _validate_close(uow: FinanceUnitOfWork) -> None:
        if uow.journal_entries.exists_unbalanced():
            raise MaterialDifferenceError(
                "Cierre bloqueado: existen asientos desbalanceados en el libro mayor"
            )
        open_reconciliations = uow.reconciliations.list_open()
        if open_reconciliations:
            raise MaterialDifferenceError(
                f"Cierre bloqueado: {len(open_reconciliations)} conciliaciones sin completar"
            )


class ReopenFiscalPeriodUseCase:
    def execute(self, connection, year: int, month: int, *, reason: str,
                operation_id: str) -> FiscalPeriod:
        with FinanceUnitOfWork(connection) as uow:
            period = uow.fiscal_periods.find_by_code(year, month)
            if period is None:
                raise FinanceDomainError(f"Fiscal period {year:04d}-{month:02d} does not exist")
            period.reopen(reason)
            uow.fiscal_periods.update(period)
            _publish(uow, EventName.FISCAL_PERIOD_REOPENED, period, operation_id)
            return period
