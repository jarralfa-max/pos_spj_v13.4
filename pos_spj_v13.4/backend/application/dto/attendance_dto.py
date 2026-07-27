"""Attendance DTOs for HR query/application boundaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AttendancePunchDTO:
    id: str
    employee_id: str
    branch_id: str
    punch_type: str
    occurred_at: str
    timezone: str
    source: str
    operation_id: str


@dataclass(frozen=True, slots=True)
class AttendanceWorkdayDTO:
    id: str
    employee_id: str
    branch_id: str
    work_date: str
    first_entry_at: str | None
    last_exit_at: str | None
    worked_minutes: int
    late_minutes: int
    overtime_minutes: int
    status: str
    source: str | None = None
    pending_incidents: int = 0
