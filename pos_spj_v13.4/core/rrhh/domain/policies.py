"""Domain policies for RRHH business rules.

These policies are deliberately small, deterministic and framework-free so
legacy services and PyQt screens can delegate business decisions without taking
a dependency on SQLite or PyQt.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional, Protocol, Tuple

from .entities import Employee, LeaveRequest


class _HasActiveFlag(Protocol):
    activo: bool


@dataclass(frozen=True)
class AttendanceHoursPolicy:
    """Calculates worked hours using the legacy RRHH time semantics."""

    time_format: str = "%H:%M"

    def calculate_worked_hours(self, start_time: str, end_time: str) -> float:
        start = datetime.strptime(start_time, self.time_format)
        end = datetime.strptime(end_time, self.time_format)
        # Preserve legacy behavior: .seconds handles same-day and overnight spans
        # as a positive modulo-24h duration.
        return max(0.0, (end - start).seconds / 3600)

    def rounded_worked_hours(self, start_time: str, end_time: str) -> float:
        return round(self.calculate_worked_hours(start_time, end_time), 2)


@dataclass(frozen=True)
class PayrollPeriodPolicy:
    """Determines the default payroll period used by the legacy UI."""

    period_days: int = 7

    def current_period(self, now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
        end = now or datetime.now()
        start = end - timedelta(days=self.period_days)
        return start, end

    def current_period_strings(self, now: Optional[datetime] = None) -> Tuple[str, str]:
        start, end = self.current_period(now)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


@dataclass(frozen=True)
class EmployeeEligibilityPolicy:
    """Employee eligibility rules for payroll-active flows."""

    def is_active(self, employee: _HasActiveFlag) -> bool:
        return bool(getattr(employee, "activo", False))

    def is_payroll_eligible(self, employee: Employee) -> bool:
        return self.is_active(employee)

    def filter_payroll_eligible(self, employees: Iterable[Employee]) -> list[Employee]:
        return [employee for employee in employees if self.is_payroll_eligible(employee)]


@dataclass(frozen=True)
class VacationOverlapPolicy:
    """Validates overlapping active vacation/permission requests."""

    blocked_statuses: tuple[str, ...] = ("aprobado", "pendiente")

    def should_validate(self, status: str) -> bool:
        return (status or "").strip().lower() in self.blocked_statuses

    def find_blocking_overlaps(self, overlaps: Iterable[LeaveRequest]) -> list[LeaveRequest]:
        return [
            leave for leave in overlaps
            if (leave.estado or "").strip().lower() in self.blocked_statuses
        ]

    def ensure_no_overlap(self, overlaps: Iterable[LeaveRequest], status: str) -> None:
        if not self.should_validate(status):
            return
        blocking = self.find_blocking_overlaps(overlaps)
        if not blocking:
            return
        first = blocking[0]
        raise ValueError(
            "El periodo solicitado se solapa con "
            f"{first.tipo} #{first.id} ({first.fecha_inicio} — {first.fecha_fin}) "
            f"en estado {first.estado}."
        )


@dataclass(frozen=True)
class AttendanceJustificationPolicy:
    """Determines whether an absence/falta should be discounted."""

    protected_leave_statuses: tuple[str, ...] = ("aprobado", "pendiente")

    def has_applicable_leave(
        self,
        absence_date: date,
        leaves: Iterable[LeaveRequest],
    ) -> bool:
        for leave in leaves:
            status = (leave.estado or "").strip().lower()
            if status not in self.protected_leave_statuses:
                continue
            try:
                start = date.fromisoformat(str(leave.fecha_inicio)[:10])
                end = date.fromisoformat(str(leave.fecha_fin)[:10])
            except Exception:
                continue
            if start <= absence_date <= end:
                return True
        return False

    def is_absence_justified(
        self,
        absence_date: date,
        leaves: Iterable[LeaveRequest] = (),
        rest_dates: Iterable[date] = (),
    ) -> bool:
        normalized_rest_dates = {
            item if isinstance(item, date) else date.fromisoformat(str(item)[:10])
            for item in rest_dates
        }
        return absence_date in normalized_rest_dates or self.has_applicable_leave(absence_date, leaves)

    def should_discount_absence(
        self,
        absence_date: date,
        leaves: Iterable[LeaveRequest] = (),
        rest_dates: Iterable[date] = (),
    ) -> bool:
        return not self.is_absence_justified(absence_date, leaves, rest_dates)


@dataclass(frozen=True)
class RestDayPolicy:
    """Rest-day and minimum-coverage rules used by RRHH audits."""

    max_consecutive_days: int = 6
    min_coverage: int = 1
    max_resting_ratio: float = 0.5

    def requires_rest(self, consecutive_days: int) -> bool:
        return consecutive_days >= self.max_consecutive_days

    def default_rest_date(self, today: Optional[date] = None) -> date:
        return (today or date.today()) + timedelta(days=1)

    def can_schedule_rest(self, resting_count: int, total_employees: int) -> bool:
        if total_employees <= 0:
            return True
        return resting_count < total_employees * self.max_resting_ratio

    def has_minimum_coverage(self, active_count: int, resting_today: int = 0) -> bool:
        return (active_count - resting_today) >= self.min_coverage
