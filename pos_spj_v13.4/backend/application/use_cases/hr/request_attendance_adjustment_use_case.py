"""Request canonical attendance punch adjustments without mutating punches."""

from __future__ import annotations

from backend.application.commands.attendance_commands import RequestAttendanceAdjustmentCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.entities import AttendanceAdjustment
from backend.domain.hr.exceptions import EmployeeNotFoundError
from backend.domain.hr.repository_ports import AttendanceAdjustmentRepositoryPort, AttendanceRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class RequestAttendanceAdjustmentUseCase(BaseUseCase[RequestAttendanceAdjustmentCommand]):
    name = "RequestAttendanceAdjustmentUseCase"

    def __init__(
        self,
        adjustment_repository: AttendanceAdjustmentRepositoryPort,
        attendance_repository: AttendanceRepositoryPort,
        *,
        event_bus: EventBus | None = None,
        permission_checker: PermissionChecker | None = None,
        audit_sink: HRAuditSink | None = None,
    ) -> None:
        self._adjustment_repository = adjustment_repository
        self._attendance_repository = attendance_repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink

    def execute(self, command: RequestAttendanceAdjustmentCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.attendance.adjust")
        original = self._attendance_repository.get_punch(command.original_punch_id)
        if original is None:
            raise EmployeeNotFoundError(command.original_punch_id)
        if command.requested_value is None or command.previous_value is None:
            raise ValueError("requested_value and previous_value are required")
        adjustment = AttendanceAdjustment(
            original_punch_id=command.original_punch_id,
            requested_value=command.requested_value,
            previous_value=command.previous_value,
            reason=command.reason.strip(),
            requested_by_user_id=command.user_id or "SYSTEM",
        )
        self._adjustment_repository.save(adjustment)
        event = create_domain_event(
            event_name=EventName.ATTENDANCE_ADJUSTMENT_REQUESTED,
            operation_id=command.operation_id,
            entity_id=adjustment.id,
            branch_id=command.branch_id,
            user_id=command.user_id,
            user_name=command.user_name,
            source_module="HR",
            payload={"original_punch_id": adjustment.original_punch_id, "employee_id": original.employee_id},
        )
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(
            self._audit_sink,
            action="HR_ATTENDANCE_ADJUSTMENT_REQUESTED",
            operation_id=command.operation_id,
            entity_id=adjustment.id,
            actor_user_id=command.user_id,
            branch_id=command.branch_id,
            metadata={"original_punch_id": adjustment.original_punch_id},
        )
        return UseCaseResult(True, command.operation_id, adjustment.id, "Corrección de asistencia solicitada.", events=(event,))
