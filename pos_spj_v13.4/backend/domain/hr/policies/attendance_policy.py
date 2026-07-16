"""Attendance sequence and idempotency policies."""

from __future__ import annotations

from backend.domain.hr.enums import PunchType
from backend.domain.hr.exceptions import AttendanceInvalidSequenceError


class AttendancePolicy:
    def validate_next_punch(self, last_punch_type: PunchType | None, next_punch_type: PunchType) -> None:
        if last_punch_type == next_punch_type:
            raise AttendanceInvalidSequenceError(f"duplicate {next_punch_type} punch")
