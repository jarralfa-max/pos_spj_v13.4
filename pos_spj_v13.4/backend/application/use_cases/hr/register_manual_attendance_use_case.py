"""Register manual HR attendance with explicit permission and reason."""

from __future__ import annotations

from backend.application.commands.attendance_commands import RegisterAttendancePunchCommand, RegisterManualAttendanceCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.application.use_cases.hr.register_attendance_punch_use_case import RegisterAttendancePunchUseCase
from backend.domain.hr.enums import AttendanceSource
from backend.domain.hr.repository_ports import AttendanceRepositoryPort, EmployeeRepositoryPort
from backend.shared.events import EventBus


class RegisterManualAttendanceUseCase(BaseUseCase[RegisterManualAttendanceCommand]):
    name = "RegisterManualAttendanceUseCase"

    def __init__(
        self,
        attendance_repository: AttendanceRepositoryPort,
        *,
        employee_repository: EmployeeRepositoryPort | None = None,
        event_bus: EventBus | None = None,
        permission_checker: PermissionChecker | None = None,
        audit_sink: HRAuditSink | None = None,
    ) -> None:
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink
        self._register_punch = RegisterAttendancePunchUseCase(
            attendance_repository,
            employee_repository=employee_repository,
            event_bus=event_bus,
            audit_sink=audit_sink,
        )

    def execute(self, command: RegisterManualAttendanceCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.attendance.register_manual")
        reason = command.reason.strip()
        notes = reason if not command.notes else f"{reason}\n{command.notes.strip()}"
        result = self._register_punch.execute(
            RegisterAttendancePunchCommand(
                operation_id=command.operation_id,
                branch_id=command.branch_id,
                user_id=command.user_id,
                user_name=command.user_name,
                employee_id=command.employee_id,
                punch_type=command.punch_type,
                occurred_at=command.occurred_at,
                timezone=command.timezone,
                source=AttendanceSource.MANUAL,
                notes=notes,
            )
        )
        if result.success and result.data.get("idempotent") is not True:
            record_hr_audit(
                self._audit_sink,
                action="HR_ATTENDANCE_MANUAL_REGISTERED",
                operation_id=command.operation_id,
                entity_id=result.entity_id or command.employee_id,
                actor_user_id=command.user_id,
                branch_id=command.branch_id,
                metadata={"reason": reason, "punch_type": command.punch_type.value},
            )
        return result
