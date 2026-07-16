"""Cash-shift HR-side use cases.

- ``ValidateCashOpenerUseCase``: blocks a cash opening when the user is not
  linked to an active employee (called by the cash open flow before opening).
- ``CloseCashShiftUseCase``: publishes the canonical CASH_SHIFT_CLOSED event
  with user_id + employee_id so the attendance handler can register the exit.

These use cases DO NOT own cash money; they express the HR contract over the
cash lifecycle. The cash register itself stays in the cash module.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.application.use_cases.hr.hr_result import HRResult
from backend.domain.hr.exceptions import (
    EmployeeInactiveError,
    UserEmployeeLinkRequiredError,
)
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class ValidateCashOpenerUseCase:
    """Ensures the opener is an active user linked to an active employee."""

    def execute(self, connection, *, user_id: str) -> HRResult:
        if not user_id:
            return HRResult.fail("Operación sin usuario autenticado", "NO_USER")
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get_by_user_id(user_id)
        if employee is None:
            return HRResult.fail(
                "El usuario no está vinculado con un empleado. No puede abrir caja.",
                "USER_NOT_LINKED")
        if not employee.active:
            return HRResult.fail(
                "El empleado vinculado está inactivo. No puede abrir caja.",
                "EMPLOYEE_INACTIVE")
        return HRResult.ok("Usuario válido para apertura de caja",
                           entity_id=employee.id, employee_id=employee.id)

    def resolve_employee_id(self, connection, *, user_id: str) -> str:
        result = self.execute(connection, user_id=user_id)
        if not result.success:
            if result.error_code == "EMPLOYEE_INACTIVE":
                raise EmployeeInactiveError(result.message)
            raise UserEmployeeLinkRequiredError(result.message)
        return result.data["employee_id"]


class CloseCashShiftUseCase:
    """Publishes CASH_SHIFT_CLOSED with the HR identity fields.

    The cash module performs the arqueo / Z-cut / shift close; this use case is
    the canonical publisher of the close event that HR attendance consumes.
    A Z-cut is not, by itself, a shift close — the caller drives this explicitly.
    """

    def execute(self, connection, *, shift_id: str, branch_id: str, user_id: str,
                employee_id: str | None = None, z_cut_id: str | None = None,
                cash_difference: float = 0.0, operation_id: str,
                closed_at: datetime | None = None, source: str = "POS") -> HRResult:
        closed_at = closed_at or datetime.now(timezone.utc)
        if employee_id is None:
            with HRUnitOfWork(connection) as uow:
                employee = uow.employees.get_by_user_id(user_id)
            if employee is None:
                return HRResult.fail(
                    "El usuario no está vinculado con un empleado", "USER_NOT_LINKED",
                    operation_id=operation_id)
            employee_id = employee.id

        with HRUnitOfWork(connection) as uow:
            uow.outbox.enqueue(new_uuid(), EventName.CASH_SHIFT_CLOSED.value, json.dumps({
                "event_id": new_uuid(),
                "operation_id": operation_id,
                "shift_id": shift_id,
                "branch_id": branch_id,
                "user_id": user_id,
                "employee_id": employee_id,
                "closed_at": closed_at.isoformat(),
                "z_cut_id": z_cut_id,
                "cash_difference": str(cash_difference),
                "source": source,
            }), operation_id)
        return HRResult.ok("Turno de caja cerrado", entity_id=shift_id,
                           operation_id=operation_id, employee_id=employee_id)
