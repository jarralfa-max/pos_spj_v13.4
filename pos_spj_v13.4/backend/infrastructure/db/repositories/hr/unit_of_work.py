"""HRUnitOfWork — one transaction boundary for the HR bounded context.

Guarantees atomicity between entity, punch/workday, audit and outbox.
Repositories never commit; the UoW owns the boundary.

Auditoría RRHH cebf67a HR-26: cada UoW confirmaba al salir, así que un caso de
uso ejecutado DENTRO de otra transacción (el manejador de Caja que registra la
asistencia y marca el evento procesado) confirmaba a medias y el rollback del
llamador ya no lo deshacía. Ahora sólo la UoW más externa de la conexión es la
dueña de la transacción; las anidadas participan en ella.
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
    SalaryHistoryRepository,
)
from backend.infrastructure.db.repositories.hr.extended_repositories import (
    EmployeeLoanRepository,
    LeaveLedgerRepository,
    PayrollInputRepository,
    TimeClockRepository,
)
from backend.infrastructure.db.repositories.hr.shift_leave_payroll_repository import (
    LeaveRepository,
    PayrollPaymentRepository,
    PayrollRepository,
    WorkShiftRepository,
)
from backend.infrastructure.db.repositories.hr.support_repositories import (
    HRAuditRepository,
    HRCalendarRepository,
    HRInboxRepository,
    HROutboxRepository,
    HRProcessedEventRepository,
)
from backend.infrastructure.db.transaction import TransactionalUnitOfWork


class HRUnitOfWork(TransactionalUnitOfWork):
    """Context manager: commit al salir limpio, rollback ante excepción — sólo
    si es la DUEÑA de la transacción (la más externa de su conexión)."""

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
        self.salary_history = SalaryHistoryRepository(connection)
        self.inbox = HRInboxRepository(connection)
        self.calendar = HRCalendarRepository(connection)
        self.time_clock = TimeClockRepository(connection)
        self.payroll_inputs = PayrollInputRepository(connection)
        self.loans = EmployeeLoanRepository(connection)
        self.leave_ledger = LeaveLedgerRepository(connection)
        self._completed = False
