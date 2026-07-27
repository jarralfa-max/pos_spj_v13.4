"""Work-shift labor calculations for late arrivals and overtime."""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.domain.hr.entities import WorkShift


class ShiftPolicy:
    """Domain policy for tolerance, lateness and overtime calculations."""

    def scheduled_start(self, work_shift: WorkShift, entry_at: datetime) -> datetime:
        return datetime.combine(entry_at.date(), work_shift.start_time, tzinfo=entry_at.tzinfo)

    def scheduled_end(self, work_shift: WorkShift, entry_at: datetime) -> datetime:
        end_date = entry_at.date()
        if work_shift.crosses_midnight:
            end_date = end_date + timedelta(days=1)
        return datetime.combine(end_date, work_shift.end_time, tzinfo=entry_at.tzinfo)

    def late_minutes(self, work_shift: WorkShift, entry_at: datetime) -> int:
        tolerated_start = self.scheduled_start(work_shift, entry_at) + timedelta(minutes=work_shift.late_tolerance_minutes)
        if entry_at <= tolerated_start:
            return 0
        return int((entry_at - tolerated_start).total_seconds() // 60)

    def overtime_minutes(self, work_shift: WorkShift, entry_at: datetime, exit_at: datetime) -> int:
        scheduled_end = self.scheduled_end(work_shift, entry_at)
        if exit_at <= scheduled_end:
            return 0
        return int((exit_at - scheduled_end).total_seconds() // 60)
