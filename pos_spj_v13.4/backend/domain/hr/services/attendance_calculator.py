"""Domain service for attendance calculations."""

from __future__ import annotations

from datetime import datetime


class AttendanceCalculator:
    def worked_minutes(self, first_entry_at: datetime | None, last_exit_at: datetime | None) -> int:
        if first_entry_at is None or last_exit_at is None or last_exit_at <= first_entry_at:
            return 0
        return int((last_exit_at - first_entry_at).total_seconds() // 60)
