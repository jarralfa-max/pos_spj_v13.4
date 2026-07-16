"""Leave DTOs for HR query/application boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class LeaveRequestDTO:
    id: str
    employee_id: str
    branch_id: str
    leave_type: str
    start_date: str
    end_date: str
    requested_days: Decimal
    reason: str
    status: str


@dataclass(frozen=True, slots=True)
class LeaveHistoryDTO:
    id: str
    leave_request_id: str
    previous_status: str | None
    new_status: str
    actor_user_id: str | None
    reason: str | None
    operation_id: str
    created_at: str
