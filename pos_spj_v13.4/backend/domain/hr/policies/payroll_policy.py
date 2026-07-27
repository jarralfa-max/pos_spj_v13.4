"""Payroll state transition policies."""

from __future__ import annotations

from backend.domain.hr.enums import PayrollRunStatus
from backend.domain.hr.exceptions import PayrollAlreadyPaidError, PayrollInvalidStateError, PayrollNotAuthorizedError


class PayrollPolicy:
    def ensure_can_authorize(self, status: PayrollRunStatus) -> None:
        if status not in (PayrollRunStatus.CALCULATED, PayrollRunStatus.UNDER_REVIEW):
            raise PayrollInvalidStateError("payroll run must be calculated before authorization")

    def ensure_can_pay(self, status: PayrollRunStatus) -> None:
        if status == PayrollRunStatus.PAID:
            raise PayrollAlreadyPaidError("payroll run is already paid")
        if status != PayrollRunStatus.AUTHORIZED:
            raise PayrollNotAuthorizedError("payroll run must be authorized before payment")

    def ensure_can_cancel(self, status: PayrollRunStatus) -> None:
        if status == PayrollRunStatus.PAID:
            raise PayrollAlreadyPaidError("paid payroll run cannot be cancelled")
        if status == PayrollRunStatus.CANCELLED:
            raise PayrollInvalidStateError("payroll run is already cancelled")
