"""Approve attendance adjustments while preserving original immutable punches."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.application.commands.attendance_commands import ApproveAttendanceAdjustmentCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.enums import AdjustmentStatus
from backend.domain.hr.exceptions import AttendanceAdjustmentNotAuthorizedError
from backend.domain.hr.repository_ports import AttendanceAdjustmentRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class ApproveAttendanceAdjustmentUseCase(BaseUseCase[ApproveAttendanceAdjustmentCommand]):
    name = "ApproveAttendanceAdjustmentUseCase"

    def __init__(
        self,
        adjustment_repository: AttendanceAdjustmentRepositoryPort,
        *,
        event_bus: EventBus | None = None,
        permission_checker: PermissionChecker | None = None,
        audit_sink: HRAuditSink | None = None,
    ) -> None:
        self._adjustment_repository = adjustment_repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink

    def execute(self, command: ApproveAttendanceAdjustmentCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.attendance.approve_adjustment")
        adjustment = self._adjustment_repository.get(command.adjustment_id)
        if adjustment is None:
            raise AttendanceAdjustmentNotAuthorizedError(command.adjustment_id)
        if adjustment.status != AdjustmentStatus.PENDING:
            return UseCaseResult(
                success=True,
                operation_id=command.operation_id,
                entity_id=adjustment.id,
                message="La corrección ya fue resuelta; se devolvió resultado idempotente.",
                data={"idempotent": True, "status": adjustment.status.value},
            )
        adjustment.status = AdjustmentStatus.APPROVED
        adjustment.approved_by_user_id = command.user_id
        adjustment.approved_at = datetime.now(UTC)
        self._adjustment_repository.update_status(adjustment)
        event = create_domain_event(
            event_name=EventName.ATTENDANCE_ADJUSTMENT_APPROVED,
            operation_id=command.operation_id,
            entity_id=adjustment.id,
            branch_id=command.branch_id,
            user_id=command.user_id,
            user_name=command.user_name,
            source_module="HR",
            payload={"original_punch_id": adjustment.original_punch_id},
        )
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(
            self._audit_sink,
            action="HR_ATTENDANCE_ADJUSTMENT_APPROVED",
            operation_id=command.operation_id,
            entity_id=adjustment.id,
            actor_user_id=command.user_id,
            branch_id=command.branch_id,
            metadata={"original_punch_id": adjustment.original_punch_id},
        )
        return UseCaseResult(True, command.operation_id, adjustment.id, "Corrección de asistencia aprobada.", events=(event,))
