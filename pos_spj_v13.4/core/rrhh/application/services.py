"""Application services for the RRHH bounded context.

Phase 5 keeps these services compatibility-oriented while delegating business
rules to domain policies and publishing validated RRHH events from the
application layer, never from PyQt UI code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.rrhh.events import (
    AttendanceEventPayload,
    EmployeeCreatedPayload,
    EmployeeDeactivatedPayload,
    EmployeeEventPayload,
    LeaveApprovedPayload,
    LeaveEventPayload,
    LeaveRejectedPayload,
    PermissionApprovedPayload,
    PermissionRequestedPayload,
    RRHHEventPublisher,
    new_operation_id,
)
from core.rrhh.domain import (
    AttendanceHoursPolicy,
    Employee,
    EmployeeEligibilityPolicy,
    LeaveRequest,
    ShiftAssignment,
    ShiftRole,
    VacationOverlapPolicy,
)
from .repositories import (
    AttendanceRepository,
    EmployeeRepository,
    LeaveRepository,
    ShiftRepository,
)


@dataclass(frozen=True)
class AttendanceActionResult:
    """Result returned by the legacy-compatible attendance check-in/out flow."""

    ok: bool
    action: str
    message: str
    attendance_id: int = 0
    hours: float = 0.0


class EmployeeApplicationService:
    """Use-case facade for employee CRUD paths used by the legacy RRHH UI."""

    def __init__(
        self,
        repository: EmployeeRepository,
        eligibility_policy: Optional[EmployeeEligibilityPolicy] = None,
        event_publisher: Optional[RRHHEventPublisher] = None,
    ):
        self.repository = repository
        self.eligibility_policy = eligibility_policy or EmployeeEligibilityPolicy()
        self.event_publisher = event_publisher or RRHHEventPublisher()

    def get_employee(self, employee_id: int) -> Optional[Employee]:
        return self.repository.get_by_id(employee_id)

    def list_active_employees(self, limit: int = 500, search: str = "") -> List[Employee]:
        return self.repository.list_active(limit=limit, search=search)

    def list_employee_lookup(self) -> List[Employee]:
        return self.repository.list_for_lookup()

    def list_payroll_eligible_employees(self) -> List[Employee]:
        return self.eligibility_policy.filter_payroll_eligible(
            self.repository.list_for_lookup()
        )

    def is_payroll_eligible(self, employee_id: int) -> bool:
        employee = self.repository.get_by_id(employee_id)
        return bool(employee and self.eligibility_policy.is_payroll_eligible(employee))

    def save_employee(
        self,
        data: Dict[str, Any],
        employee_id: Optional[int] = None,
        operation_id: Optional[str] = None,
    ) -> int:
        op_id = operation_id or new_operation_id("empleado")
        if employee_id:
            self.repository.update(employee_id, data)
            saved_id = int(employee_id)
            self.event_publisher.publish(
                EmployeeEventPayload(
                    operation_id=op_id,
                    employee_id=saved_id,
                    nombre=str(data.get("nombre", "")),
                    puesto=str(data.get("puesto", "")),
                    changes=dict(data),
                )
            )
            return saved_id

        saved_id = self.repository.create(data)
        self.event_publisher.publish(
            EmployeeCreatedPayload(
                operation_id=op_id,
                employee_id=saved_id,
                nombre=str(data.get("nombre", "")),
                puesto=str(data.get("puesto", "")),
            )
        )
        return saved_id

    def deactivate_employee(
        self, employee_id: int, reason: str = "", operation_id: Optional[str] = None
    ) -> None:
        op_id = operation_id or new_operation_id("empleado-baja")
        employee = self.repository.get_by_id(employee_id)
        self.repository.deactivate(employee_id)
        self.event_publisher.publish(
            EmployeeDeactivatedPayload(
                operation_id=op_id,
                employee_id=employee_id,
                nombre=employee.nombre_completo if employee else "",
                puesto=employee.puesto if employee else "",
                sucursal_id=employee.sucursal_id if employee else None,
                reason=reason,
            )
        )


class AttendanceApplicationService:
    """Use-case facade for legacy attendance list and check-in/out behavior."""

    def __init__(
        self,
        repository: AttendanceRepository,
        hours_policy: Optional[AttendanceHoursPolicy] = None,
        event_publisher: Optional[RRHHEventPublisher] = None,
    ):
        self.repository = repository
        self.hours_policy = hours_policy or AttendanceHoursPolicy()
        self.event_publisher = event_publisher or RRHHEventPublisher()

    def list_attendance_table_rows(
        self,
        date_from: str,
        date_to: str,
        employee_id: Optional[int] = None,
        limit: int = 300,
    ) -> List[tuple]:
        return self.repository.list_between_for_table(date_from, date_to, employee_id, limit=limit)

    def get_status_for_date(self, employee_id: int, fecha: str):
        return self.repository.get_for_date(employee_id, fecha)

    def register_check_in_out(
        self,
        employee_id: int,
        fecha: str,
        hora: str,
        operation_id: Optional[str] = None,
    ) -> AttendanceActionResult:
        op_id = operation_id or new_operation_id("asistencia")
        current = self.repository.get_for_date(employee_id, fecha)
        if not current:
            attendance_id = self.repository.register_check_in(employee_id, fecha, hora, estado="PRESENTE")
            self.event_publisher.publish(
                AttendanceEventPayload(
                    operation_id=op_id,
                    attendance_id=attendance_id,
                    employee_id=employee_id,
                    fecha=fecha,
                    tipo="check_in",
                    hora=hora,
                )
            )
            return AttendanceActionResult(
                ok=True,
                action="check_in",
                message=f"✅ Entrada registrada: {hora}",
                attendance_id=attendance_id,
            )

        if current.hora_entrada and not current.hora_salida:
            hours = self.hours_policy.calculate_worked_hours(current.hora_entrada, hora)
            rounded = round(hours, 2)
            self.repository.register_check_out(current.id, hora, rounded)
            self.event_publisher.publish(
                AttendanceEventPayload(
                    operation_id=op_id,
                    attendance_id=current.id,
                    employee_id=employee_id,
                    fecha=fecha,
                    tipo="check_out",
                    hora=hora,
                    hours=rounded,
                )
            )
            return AttendanceActionResult(
                ok=True,
                action="check_out",
                message=f"✅ Salida registrada: {hora} ({hours:.1f}h)",
                attendance_id=current.id,
                hours=rounded,
            )

        return AttendanceActionResult(
            ok=False,
            action="complete",
            message="Jornada ya completa para hoy.",
            attendance_id=current.id,
            hours=float(current.horas_trabajadas or 0),
        )


class LeaveApplicationService:
    """Use-case facade for legacy vacations/permissions UI paths."""

    def __init__(
        self,
        repository: LeaveRepository,
        overlap_policy: Optional[VacationOverlapPolicy] = None,
        event_publisher: Optional[RRHHEventPublisher] = None,
    ):
        self.repository = repository
        self.overlap_policy = overlap_policy or VacationOverlapPolicy()
        self.event_publisher = event_publisher or RRHHEventPublisher()

    def list_leave_table_rows(self, limit: int = 200) -> List[tuple]:
        return self.repository.list_recent_for_table(limit=limit)

    def create_leave(
        self,
        employee_id: int,
        leave_type: str,
        date_from: str,
        date_to: str,
        days: int,
        status: str,
        operation_id: Optional[str] = None,
    ) -> int:
        op_id = operation_id or new_operation_id("licencia")
        overlaps = self.repository.find_overlaps(employee_id, date_from, date_to)
        self.overlap_policy.ensure_no_overlap(overlaps, status)
        request_id = self.repository.create(
            {
                "personal_id": employee_id,
                "tipo": leave_type,
                "fecha_inicio": date_from,
                "fecha_fin": date_to,
                "dias": days,
                "estado": status,
            }
        )
        self.event_publisher.publish(
            self._leave_payload_for_status(
                operation_id=op_id,
                request_id=request_id,
                employee_id=employee_id,
                leave_type=leave_type,
                date_from=date_from,
                date_to=date_to,
                days=days,
                status=status,
            )
        )
        return request_id

    def _leave_payload_for_status(
        self,
        operation_id: str,
        request_id: int,
        employee_id: int,
        leave_type: str,
        date_from: str,
        date_to: str,
        days: int,
        status: str,
    ) -> LeaveEventPayload:
        normalized_type = (leave_type or "").strip().lower()
        normalized_status = (status or "").strip().lower()
        payload_kwargs = {
            "operation_id": operation_id,
            "request_id": request_id,
            "employee_id": employee_id,
            "tipo": leave_type,
            "date_start": date_from,
            "date_end": date_to,
            "days": days,
            "status": status,
        }
        if normalized_type == "permiso" and normalized_status == "aprobado":
            return PermissionApprovedPayload(**payload_kwargs)
        if normalized_type == "permiso":
            return PermissionRequestedPayload(**payload_kwargs)
        if normalized_status == "aprobado":
            return LeaveApprovedPayload(**payload_kwargs)
        if normalized_status == "rechazado":
            return LeaveRejectedPayload(**payload_kwargs)
        return LeaveEventPayload(**payload_kwargs)

    def update_status(self, leave_id: int, status: str) -> None:
        self.repository.update_status(leave_id, status)

    def find_overlaps(
        self,
        employee_id: int,
        date_from: str,
        date_to: str,
        exclude_id: Optional[int] = None,
    ) -> List[LeaveRequest]:
        return self.repository.find_overlaps(employee_id, date_from, date_to, exclude_id=exclude_id)


class ShiftApplicationService:
    """Use-case facade for shift roles and assignments.

    It is intentionally not wired to the PyQt screen yet; this keeps phase 3
    additive while making the application layer available for the next phase.
    """

    def __init__(self, repository: ShiftRepository):
        self.repository = repository

    def list_roles(self, active_only: bool = True) -> List[ShiftRole]:
        return self.repository.list_roles(active_only=active_only)

    def save_role(self, data: Dict[str, Any], role_id: Optional[int] = None) -> int:
        if role_id:
            self.repository.update_role(role_id, data)
            return int(role_id)
        return self.repository.create_role(data)

    def deactivate_role(self, role_id: int) -> None:
        self.repository.deactivate_role(role_id)

    def list_assignments(self, active_only: bool = True) -> List[ShiftAssignment]:
        return self.repository.list_assignments(active_only=active_only)

    def save_assignment(self, data: Dict[str, Any], assignment_id: Optional[int] = None) -> int:
        if assignment_id:
            self.repository.update_assignment(assignment_id, data)
            return int(assignment_id)
        return self.repository.create_assignment(data)

    def deactivate_assignment(self, assignment_id: int) -> None:
        self.repository.deactivate_assignment(assignment_id)
