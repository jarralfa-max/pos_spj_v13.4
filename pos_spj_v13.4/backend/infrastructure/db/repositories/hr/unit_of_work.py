"""HRUnitOfWork — one transaction boundary for the HR bounded context.

Guarantees atomicity between entity, punch/workday, audit and outbox.
Repositories never commit; the UoW owns the boundary.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.hr.attendance_repository import (
    AttendanceAdjustmentRepository,
    AttendanceRepository,
)
from backend.infrastructure.db.repositories.hr.employee_repository import (
    DepartmentRepository,
    EmployeeRepository,
    PositionRepository,
)
from backend.infrastructure.db.repositories.hr.shift_leave_payroll_repository import (
    LeaveRepository,
    PayrollPaymentRepository,
    PayrollRepository,
    WorkShiftRepository,
)
from backend.infrastructure.db.repositories.hr.support_repositories import (
    HRAuditRepository,
    HROutboxRepository,
    HRProcessedEventRepository,
)


class HRUnitOfWork:
    """Context manager: commits on clean exit, rolls back on exception."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.employees = EmployeeRepository(connection)
        self.departments = DepartmentRepository(connection)
        self.positions = PositionRepository(connection)
        self.attendance = AttendanceRepository(connection)
        self.adjustments = AttendanceAdjustmentRepository(connection)
        self.shifts = WorkShiftRepository(connection)
        self.leaves = LeaveRepository(connection)
        self.payroll = PayrollRepository(connection)
        self.payroll_payments = PayrollPaymentRepository(connection)
        self.audit = HRAuditRepository(connection)
        self.processed_events = HRProcessedEventRepository(connection)
        self.outbox = HROutboxRepository(connection)
        self._completed = False

    def __enter__(self) -> "HRUnitOfWork":
        self._completed = False
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._completed:
            self.commit()
        return False

    def commit(self) -> None:
        self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        rollback = getattr(self.connection, "rollback", None)
        if rollback is not None:
            rollback()
        self._completed = True
