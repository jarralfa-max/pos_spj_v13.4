"""Leave request policies."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.hr.exceptions import InsufficientLeaveBalanceError, LeaveOverlapError


class LeavePolicy:
    def ensure_valid_range(self, start: date, end: date) -> None:
        if end < start:
            raise ValueError("leave end date cannot be before start date")

    def requested_days(self, start: date, end: date) -> Decimal:
        self.ensure_valid_range(start, end)
        return Decimal((end - start).days + 1)

    def ensure_no_overlap(self, start: date, end: date, approved_ranges: list[tuple[date, date]]) -> None:
        for existing_start, existing_end in approved_ranges:
            if start <= existing_end and end >= existing_start:
                raise LeaveOverlapError("leave request overlaps an existing approved or pending leave")

    def ensure_balance(self, available_days: Decimal, requested_days: Decimal) -> None:
        if available_days < requested_days:
            raise InsufficientLeaveBalanceError("insufficient leave balance")
