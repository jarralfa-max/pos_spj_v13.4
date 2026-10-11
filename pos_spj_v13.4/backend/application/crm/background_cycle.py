"""Ciclo de fondo del CRM (CRM-43).

Lo que en el CRM depende del reloj y no de una acción de alguien:

* los disparadores por tiempo de las automatizaciones (§56): prospecto u
  oportunidad sin movimiento, oportunidad vencida, cliente inactivo, SLA en
  riesgo o vencido, revisión de crédito;
* la entrega de los recordatorios cuya hora ya llegó;
* el vencimiento de las cotizaciones cuya vigencia pasó.

La aplicación de escritorio lo corre al iniciar sesión y luego cada pocos
minutos (``frontend/desktop/shell/background``). Cada parte falla por su
cuenta: un error en una no impide la otra ni tumba la aplicación.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.shared.ids import new_uuid

_LOG = logging.getLogger("spj.crm.background")


@dataclass(frozen=True, slots=True)
class CRMBackgroundCycleResult:
    automation_executions: int
    reminders_delivered: int
    errors: tuple[str, ...] = ()
    quotes_expired: int = 0


def run_crm_background_cycle(connection, *, now: datetime | None = None) -> CRMBackgroundCycleResult:
    from backend.application.crm.use_cases.automation_use_cases import (
        EvaluateTimeBasedAutomationTriggersUseCase,
    )
    from backend.application.crm.use_cases.reminder_use_cases import (
        DispatchDueCRMRemindersUseCase,
    )

    now = now or datetime.now(timezone.utc)
    errors: list[str] = []
    executions = 0
    delivered = 0
    try:
        executions = len(EvaluateTimeBasedAutomationTriggersUseCase().execute(
            connection, operation_id=f"crm-sweep-{new_uuid()}", now=now))
    except Exception as exc:  # noqa: BLE001 — el ciclo nunca tumba la aplicación
        _rollback(connection)
        errors.append(f"automatizaciones: {exc}")
        _LOG.exception("Falló la evaluación de automatizaciones por tiempo")
    try:
        delivered = DispatchDueCRMRemindersUseCase().execute(
            connection, now=now.isoformat(timespec="seconds"))
    except Exception as exc:  # noqa: BLE001
        _rollback(connection)
        errors.append(f"recordatorios: {exc}")
        _LOG.exception("Falló la entrega de recordatorios del CRM")
    expired = 0
    try:
        from backend.application.quotes.use_cases.quote_use_cases import ExpireQuotesUseCase
        expired = ExpireQuotesUseCase().execute(connection, today=now.astimezone().date())
    except Exception as exc:  # noqa: BLE001
        _rollback(connection)
        errors.append(f"cotizaciones: {exc}")
        _LOG.exception("Falló el vencimiento de cotizaciones")
    return CRMBackgroundCycleResult(executions, delivered, tuple(errors), expired)


def _rollback(connection) -> None:
    try:
        connection.rollback()
    except Exception:  # noqa: BLE001
        pass
