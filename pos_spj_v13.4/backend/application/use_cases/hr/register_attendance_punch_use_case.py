"""Register immutable attendance punches and enforce sequence idempotency."""

from __future__ import annotations

from backend.application.commands.attendance_commands import RecalculateWorkdayCommand, RegisterAttendancePunchCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.recalculate_workday_use_case import RecalculateWorkdayUseCase
from backend.domain.hr.entities import AttendanceIncident, AttendancePunch
from backend.domain.hr.enums import AttendanceIncidentType, PunchType
from backend.domain.hr.exceptions import EmployeeInactiveError, EmployeeNotFoundError
from backend.domain.hr.repository_ports import AttendanceRepositoryPort, EmployeeRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class RegisterAttendancePunchUseCase(BaseUseCase[RegisterAttendancePunchCommand]):
    name = "RegisterAttendancePunchUseCase"

    def __init__(
        self,
        attendance_repository: AttendanceRepositoryPort,
        *,
        employee_repository: EmployeeRepositoryPort | None = None,
        event_bus: EventBus | None = None,
        audit_sink: HRAuditSink | None = None,
    ) -> None:
        self._attendance_repository = attendance_repository
        self._employee_repository = employee_repository
        self._event_bus = event_bus
        self._audit_sink = audit_sink
        self._recalculate = RecalculateWorkdayUseCase(attendance_repository)

    def execute(self, command: RegisterAttendancePunchCommand) -> UseCaseResult:
        command.validate_context()
        occurred_at = command.occurred_at
        if occurred_at is None:
            raise ValueError("occurred_at is required")
        if self._employee_repository is not None:
            employee = self._employee_repository.get(command.employee_id)
            if employee is None:
                raise EmployeeNotFoundError(command.employee_id)
            if not employee.active:
                raise EmployeeInactiveError(command.employee_id)
        existing_by_operation = self._attendance_repository.get_punch_by_operation_id(command.operation_id)
        if existing_by_operation is not None:
            return UseCaseResult(
                success=True,
                operation_id=command.operation_id,
                entity_id=existing_by_operation.id,
                message="Operación de asistencia ya registrada; se devolvió resultado idempotente.",
                data={"idempotent": True, "punch_type": existing_by_operation.punch_type.value},
            )
        if command.source_reference_id:
            existing_by_source = self._attendance_repository.get_punch_by_source_reference(
                command.source.value,
                command.source_reference_id,
                command.punch_type.value,
            )
            if existing_by_source is not None:
                return UseCaseResult(
                    success=True,
                    operation_id=command.operation_id,
                    entity_id=existing_by_source.id,
                    message="La marcación fuente ya existía; no se creó duplicado.",
                    data={"idempotent": True, "source_reference_id": command.source_reference_id},
                )
        punches = self._attendance_repository.list_punches_for_workday(
            employee_id=command.employee_id,
            branch_id=command.branch_id,
            work_date=occurred_at.date(),
        )
        open_entry = self._has_open_entry(punches)
        if command.punch_type == PunchType.ENTRY and open_entry:
            incident = AttendanceIncident(
                employee_id=command.employee_id,
                branch_id=command.branch_id,
                work_date=occurred_at.date(),
                incident_type=AttendanceIncidentType.DUPLICATE_IGNORED,
                operation_id=command.operation_id,
                source_reference_id=command.source_reference_id,
                notes="Entrada ignorada porque ya existe una entrada laboral abierta.",
            )
            self._attendance_repository.add_incident(incident)
            event = self._publish_incident(command, incident)
            return UseCaseResult(
                success=True,
                operation_id=command.operation_id,
                entity_id=incident.id,
                message="Ya existía una entrada laboral registrada; no se creó un duplicado.",
                data={"idempotent": True, "incident_type": incident.incident_type.value},
                events=(event,) if event is not None else (),
            )
        if command.punch_type == PunchType.EXIT and not open_entry:
            incident = AttendanceIncident(
                employee_id=command.employee_id,
                branch_id=command.branch_id,
                work_date=occurred_at.date(),
                incident_type=AttendanceIncidentType.MISSING_ENTRY,
                operation_id=command.operation_id,
                source_reference_id=command.source_reference_id,
                notes="Salida ignorada porque no existe una entrada laboral abierta.",
            )
            self._attendance_repository.add_incident(incident)
            event = self._publish_incident(command, incident)
            return UseCaseResult(
                success=True,
                operation_id=command.operation_id,
                entity_id=incident.id,
                message="No se encontró una entrada laboral. Se creó una incidencia para revisión de RRHH.",
                data={"incident_type": incident.incident_type.value},
                events=(event,) if event is not None else (),
            )
        punch = AttendancePunch(
            employee_id=command.employee_id,
            branch_id=command.branch_id,
            punch_type=command.punch_type,
            occurred_at=occurred_at,
            timezone=command.timezone,
            source=command.source,
            source_reference_id=command.source_reference_id,
            device_id=command.device_id,
            registered_by_user_id=command.user_id,
            operation_id=command.operation_id,
            notes=command.notes,
        )
        self._attendance_repository.add_punch(punch)
        recalc_result = self._recalculate.execute(
            RecalculateWorkdayCommand(
                operation_id=command.operation_id,
                branch_id=command.branch_id,
                user_id=command.user_id,
                user_name=command.user_name,
                employee_id=command.employee_id,
                work_date=occurred_at.date(),
            )
        )
        events = self._publish_punch_events(command, punch)
        record_hr_audit(
            self._audit_sink,
            action="HR_ATTENDANCE_PUNCH_REGISTERED",
            operation_id=command.operation_id,
            entity_id=punch.id,
            actor_user_id=command.user_id,
            branch_id=command.branch_id,
            metadata={"punch_type": punch.punch_type.value, "source": punch.source.value},
        )
        message = "Entrada registrada correctamente." if punch.punch_type == PunchType.ENTRY else "Salida registrada correctamente."
        return UseCaseResult(
            success=True,
            operation_id=command.operation_id,
            entity_id=punch.id,
            message=message,
            data={"workday_id": recalc_result.entity_id, "punch_type": punch.punch_type.value},
            events=events,
        )

    def _has_open_entry(self, punches: list[AttendancePunch]) -> bool:
        balance = 0
        for punch in punches:
            if punch.punch_type == PunchType.ENTRY:
                balance += 1
            elif punch.punch_type == PunchType.EXIT and balance > 0:
                balance -= 1
        return balance > 0

    def _publish_punch_events(self, command: RegisterAttendancePunchCommand, punch: AttendancePunch):
        event_names = [EventName.ATTENDANCE_PUNCH_REGISTERED]
        event_names.append(EventName.ATTENDANCE_ENTRY_REGISTERED if punch.punch_type == PunchType.ENTRY else EventName.ATTENDANCE_EXIT_REGISTERED)
        events = tuple(
            create_domain_event(
                event_name=event_name,
                operation_id=command.operation_id,
                entity_id=punch.id,
                branch_id=command.branch_id,
                user_id=command.user_id,
                user_name=command.user_name,
                source_module="HR",
                payload={
                    "employee_id": punch.employee_id,
                    "punch_type": punch.punch_type.value,
                    "occurred_at": punch.occurred_at.isoformat(),
                    "source": punch.source.value,
                },
            )
            for event_name in event_names
        )
        if self._event_bus is not None:
            for event in events:
                self._event_bus.publish(event)
        return events

    def _publish_incident(self, command: RegisterAttendancePunchCommand, incident: AttendanceIncident):
        event = create_domain_event(
            event_name=EventName.ATTENDANCE_INCIDENT_CREATED,
            operation_id=command.operation_id,
            entity_id=incident.id,
            branch_id=command.branch_id,
            user_id=command.user_id,
            user_name=command.user_name,
            source_module="HR",
            payload={"employee_id": incident.employee_id, "incident_type": incident.incident_type.value},
        )
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(
            self._audit_sink,
            action="HR_ATTENDANCE_INCIDENT_CREATED",
            operation_id=command.operation_id,
            entity_id=incident.id,
            actor_user_id=command.user_id,
            branch_id=command.branch_id,
            metadata={"incident_type": incident.incident_type.value},
        )
        return event
