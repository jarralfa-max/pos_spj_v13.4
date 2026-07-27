"""Dashboard DTOs for the HR module."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class HRDashboardDTO:
    active_employees: int
    present_staff: int
    today_absences: int
    late_arrivals: int
    pending_requests: int
    overtime_minutes: int
    estimated_payroll_cost: Decimal
    pending_incidents: int
