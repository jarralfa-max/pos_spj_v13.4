"""Payroll policy — state transitions and no-double-pay guarantees."""

from __future__ import annotations

from backend.domain.hr.entities import PayrollRun
from backend.domain.hr.enums import PayrollRunStatus
from backend.domain.hr.exceptions import (
    PayrollAlreadyPaidError,
    PayrollNotAuthorizedError,
)


class PayrollPolicy:
    def enforce_can_authorize(self, run: PayrollRun, authorizer_user_id: str) -> None:
        if run.status not in (PayrollRunStatus.CALCULATED, PayrollRunStatus.UNDER_REVIEW):
            raise PayrollNotAuthorizedError(
                f"Solo se autoriza una corrida CALCULATED/UNDER_REVIEW (está {run.status.value})"
            )
        if run.generated_by_user_id and authorizer_user_id == run.generated_by_user_id:
            from backend.domain.hr.exceptions import HRDomainError
            raise HRDomainError("Separación de funciones: quien genera no autoriza")

    def enforce_can_pay(self, run: PayrollRun) -> None:
        if run.status is PayrollRunStatus.PAID:
            raise PayrollAlreadyPaidError("La corrida ya fue pagada; no se paga dos veces")
        if run.status is not PayrollRunStatus.AUTHORIZED:
            raise PayrollNotAuthorizedError("La corrida debe estar AUTHORIZED para pagarse")
        if run.net_amount().is_negative():
            from backend.domain.hr.exceptions import PayrollInvalidStateError
            raise PayrollInvalidStateError("El neto de la corrida no puede ser negativo")
