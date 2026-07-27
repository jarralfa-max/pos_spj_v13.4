"""Commands for canonical HR attendance use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from backend.application.commands.base_command import BaseCommand
from backend.domain.hr.enums import AttendanceSource, PunchType


@dataclass(frozen=True)
class RecalculateWorkdayCommand(BaseCommand):
    employee_id: str = ""
    work_date: date | None = None

    def validate_context(self) -> None:
        super().validate_context()
        if not self.employee_id:
            raise ValueError("employee_id is required")
        if self.work_date is None:
            raise ValueError("work_date is required")


@dataclass(frozen=True)
class RegisterAttendancePunchCommand(BaseCommand):
    employee_id: str = ""
    punch_type: PunchType = PunchType.ENTRY
    occurred_at: datetime | None = None
    timezone: str = "America/Mexico_City"
    source: AttendanceSource = AttendanceSource.SYSTEM
    source_reference_id: str | None = None
    device_id: str | None = None
    notes: str | None = None

    def validate_context(self) -> None:
        super().validate_context()
        if not self.employee_id:
            raise ValueError("employee_id is required")
        if self.occurred_at is None:
            raise ValueError("occurred_at is required")
        if not self.timezone.strip():
            raise ValueError("timezone is required")


@dataclass(frozen=True)
class RegisterManualAttendanceCommand(BaseCommand):
    employee_id: str = ""
    punch_type: PunchType = PunchType.ENTRY
    occurred_at: datetime | None = None
    timezone: str = "America/Mexico_City"
    reason: str = ""
    notes: str | None = None

    def validate_context(self) -> None:
        super().validate_context()
        if not self.employee_id:
            raise ValueError("employee_id is required")
        if self.occurred_at is None:
            raise ValueError("occurred_at is required")
        if not self.reason.strip():
            raise ValueError("reason is required")


@dataclass(frozen=True)
class RequestAttendanceAdjustmentCommand(BaseCommand):
    original_punch_id: str = ""
    requested_value: datetime | None = None
    previous_value: datetime | None = None
    reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.original_punch_id:
            raise ValueError("original_punch_id is required")
        if self.requested_value is None or self.previous_value is None:
            raise ValueError("requested_value and previous_value are required")
        if not self.reason.strip():
            raise ValueError("reason is required")


@dataclass(frozen=True)
class ApproveAttendanceAdjustmentCommand(BaseCommand):
    adjustment_id: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.adjustment_id:
            raise ValueError("adjustment_id is required")


@dataclass(frozen=True)
class RejectAttendanceAdjustmentCommand(ApproveAttendanceAdjustmentCommand):
    reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.reason.strip():
            raise ValueError("reason is required")
