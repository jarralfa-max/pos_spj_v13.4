"""DTOs for canonical HR schedule read models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkShiftDTO:
    id: str
    name: str
    start_time: str
    end_time: str
    crosses_midnight: bool
    break_minutes: int
    late_tolerance_minutes: int
    branch_id: str


@dataclass(frozen=True, slots=True)
class ShiftAssignmentDTO:
    id: str
    employee_id: str
    work_shift_id: str
    effective_from: str
    effective_to: str | None
    weekdays: str
    branch_id: str


@dataclass(frozen=True, slots=True)
class ShiftTemplateDTO:
    id: str
    name: str
    branch_id: str
    weekdays: str
    work_shift_id: str


@dataclass(frozen=True, slots=True)
class RestDayDTO:
    id: str
    employee_id: str
    branch_id: str
    rest_date: str
    reason: str
