"""Fiscal period use cases — open, soft-close, close and controlled reopen.

Monthly close validation (audit d9f2bca F16): no unbalanced entries; no open
bank reconciliation of a statement dated within or before the period (a July
statement no longer blocks closing June); subledger-vs-ledger controls are
measured and persisted; and every OPEN close exception of the period or an
earlier one (material instrument differences, subledger gaps, sale credit vs
receivable) blocks the close until it disappears or is authorized with a reason.
"""

from __future__ import annotations

import calendar
import json
import logging
from datetime import date

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
             operation_id: str, *, actor: str | None = None, reason: str | None = None) -> None:
    uow.outbox.enqueue(
        event_id=new_uuid(),
        event_name=event_name.value,
        payload_json=json.dumps({
            "fiscal_period_id": period.id,
            "period": period.period.code(),
            "status": period.status.value,
            "actor": actor,
            "reason": reason,
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
        period_code = f"{year:04d}-{month:02d}"
        period_end = date(year, month, calendar.monthrange(year, month)[1])
        # Los controles persisten sus excepciones en SU transacción: si el
        # cierre se rechaza, la evidencia de por qué queda guardada.
        from backend.application.services.finance.close_controls import FinanceCloseControls
        exceptions = FinanceCloseControls().run(connection, period_code=period_code,
                                                as_of=period_end)
        with FinanceUnitOfWork(connection) as uow:
            period = uow.fiscal_periods.find_by_code(year, month)
            if period is None:
                raise FinanceDomainError(f"Fiscal period {year:04d}-{month:02d} does not exist")
            self._validate_close(uow, period_end, exceptions)
            if soft:
                period.soft_close()
                event = EventName.FISCAL_PERIOD_SOFT_CLOSED
            else:
                period.close(closed_by)
                event = EventName.FISCAL_PERIOD_CLOSED
            uow.fiscal_periods.update(period)
            _publish(uow, event, period, operation_id, actor=closed_by)
            return period

    @staticmethod
    def _validate_close(uow: FinanceUnitOfWork, period_end: date,
                        exceptions: list[dict]) -> None:
        if uow.journal_entries.exists_unbalanced():
            raise MaterialDifferenceError(
                "Cierre bloqueado: existen asientos desbalanceados en el libro mayor"
            )
        open_reconciliations = uow.reconciliations.list_open(
            statement_date_until=period_end.isoformat())
        if open_reconciliations:
            raise MaterialDifferenceError(
                f"Cierre bloqueado: {len(open_reconciliations)} conciliaciones sin completar"
            )
        if exceptions:
            detail = "; ".join(
                f"{e['check_type']} {e['subject']} (diferencia {e['difference']})"
                for e in exceptions[:5])
            raise MaterialDifferenceError(
                f"Cierre bloqueado: {len(exceptions)} diferencias materiales sin resolver ni "
                f"autorizar — {detail}")


class AuthorizeCloseExceptionUseCase:
    """Acepta una diferencia material con motivo (quien llama exige
    ``FINANZAS.periodo.autorizar_excepcion``). Queda quién y por qué."""

    def execute(self, connection, *, exception_id: str, authorized_by: str,
                reason: str) -> None:
        if not (reason or "").strip():
            raise FinanceDomainError("Autorizar una diferencia exige el motivo")
        with FinanceUnitOfWork(connection) as uow:
            uow.close_exceptions.authorize(exception_id, authorized_by=authorized_by,
                                           reason=reason.strip())


class ReopenFiscalPeriodUseCase:
    def execute(self, connection, year: int, month: int, *, reason: str,
                operation_id: str, reopened_by: str | None = None) -> FiscalPeriod:
        with FinanceUnitOfWork(connection) as uow:
            period = uow.fiscal_periods.find_by_code(year, month)
            if period is None:
                raise FinanceDomainError(f"Fiscal period {year:04d}-{month:02d} does not exist")
            period.reopen(reason)
            uow.fiscal_periods.update(period)
            _publish(uow, EventName.FISCAL_PERIOD_REOPENED, period, operation_id,
                     actor=reopened_by, reason=reason)
            return period
