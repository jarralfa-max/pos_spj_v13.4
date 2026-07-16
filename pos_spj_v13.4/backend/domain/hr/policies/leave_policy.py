"""Leave policy — overlap and balance validation."""

from __future__ import annotations

from datetime import date

from backend.domain.hr.entities import LeaveRequest
from backend.domain.hr.enums import LeaveStatus, LeaveType
from backend.domain.hr.exceptions import (
    InsufficientLeaveBalanceError,
    InvalidLeaveDatesError,
    LeaveOverlapError,
)


class LeavePolicy:
    #: Leave types that consume the paid vacation balance.
    BALANCE_TYPES = frozenset({LeaveType.VACATION})

    def enforce_dates(self, start_date: date, end_date: date) -> None:
        if end_date < start_date:
            raise InvalidLeaveDatesError("La fecha final no puede ser anterior a la inicial")

    def enforce_no_overlap(self, new_start: date, new_end: date,
                           existing: list[LeaveRequest]) -> None:
        for request in existing:
            if request.status in (LeaveStatus.APPROVED, LeaveStatus.PENDING) \
                    and request.overlaps(new_start, new_end):
                raise LeaveOverlapError(
                    f"La solicitud se solapa con otra del {request.start_date} "
                    f"al {request.end_date}"
                )

    def enforce_balance(self, leave_type: LeaveType, requested_days: int,
                        available_days: int) -> None:
        if leave_type in self.BALANCE_TYPES and requested_days > available_days:
            raise InsufficientLeaveBalanceError(
                f"Saldo insuficiente: disponibles {available_days}, solicitados {requested_days}"
            )
