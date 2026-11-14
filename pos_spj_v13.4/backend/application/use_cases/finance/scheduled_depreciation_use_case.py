"""Corrida automática de depreciación (SDLC-FIN-004).

Decisión del responsable (2026-11-05): corre sola el día 1. Cada ciclo de fondo
pregunta por el mes que ya terminó, así que si la app estuvo apagada el día 1
corre en el primer ciclo después. La identidad de la operación se deriva del
periodo: dos disparos, aunque sean de dos estaciones, son una sola corrida.

Lo que quede fuera (periodo ya cerrado, activo completado después de la corrida)
se recupera en la siguiente corrida: los meses omitidos no se pierden (SDLC-FIN-003).
Sin usuario: ``run_by`` vacío identifica la corrida automática.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.application.use_cases.finance.run_depreciation_use_case import (
    RunDepreciationUseCase,
)
from backend.domain.finance.enums import FiscalPeriodStatus
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import derived_uuidv7


class RunScheduledDepreciationUseCase:
    def execute(self, connection, *, today: date) -> dict:
        """``{"period": "YYYY-MM", "entries": [ids de asiento]}``."""
        last_day = today.replace(day=1) - timedelta(days=1)
        period_code = f"{last_day.year:04d}-{last_day.month:02d}"
        operation_id = derived_uuidv7("scheduled-depreciation", period_code)
        with FinanceUnitOfWork(connection) as uow:
            period = uow.fiscal_periods.find_by_code(last_day.year, last_day.month)
            closed = period is not None and period.status is not FiscalPeriodStatus.OPEN
            if closed or uow.fixed_assets.find_run_by_operation_id(operation_id) is not None:
                return {"period": period_code, "entries": []}
        entries = RunDepreciationUseCase().execute(
            connection, year=last_day.year, month=last_day.month, operation_id=operation_id)
        return {"period": period_code, "entries": entries}
