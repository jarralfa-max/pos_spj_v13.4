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
    DriverAssignedPayload,
    EmployeeCreatedPayload,
    EmployeeDeactivatedPayload,
    EmployeeEventPayload,
    LeaveApprovedPayload,
    LeaveEventPayload,
    LeaveRejectedPayload,
    PayrollGeneratedPayload,
    PayrollPaidPayload,
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
    EmployeeIdentityRepository,
    EmployeeRepository,
    LeaveRepository,
    PayrollRepository,
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
            saved_id = employee_id  # UUIDv7 (sin cast)
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


@dataclass(frozen=True)
class PayrollPaymentCommand:
    """Formal command for registering and publishing a payroll payment."""

    employee_id: int
    period_start: str
    period_end: str
    total: float
    sucursal_id: int
    neto: Optional[float] = None
    salario_base: float = 0.0
    bonos: float = 0.0
    deducciones: float = 0.0
    metodo_pago: str = "efectivo"
    usuario: str = ""
    operation_id: str = ""
    source_id: Optional[int] = None


@dataclass(frozen=True)
class PayrollApplicationResult:
    ok: bool
    payroll_payment_id: int
    employee_id: int
    total: float
    neto: float
    operation_id: str
    created: bool = True
    error: str = ""


class PayrollApplicationService:
    """Formal payroll application service for phase 10.

    It owns payroll payment registration, employee eligibility checks and
    canonical RRHH payroll event publishing. Legacy UIs can keep calling current
    use cases while this service becomes the stable Application layer boundary.
    """

    def __init__(
        self,
        payroll_repository: PayrollRepository,
        employee_repository: EmployeeRepository,
        eligibility_policy: Optional[EmployeeEligibilityPolicy] = None,
        event_publisher: Optional[RRHHEventPublisher] = None,
    ):
        self.payroll_repository = payroll_repository
        self.employee_repository = employee_repository
        self.eligibility_policy = eligibility_policy or EmployeeEligibilityPolicy()
        self.event_publisher = event_publisher or RRHHEventPublisher()

    def pay_payroll(self, command: PayrollPaymentCommand) -> PayrollApplicationResult:
        op_id = str(command.operation_id or "").strip() or new_operation_id("nomina")
        try:
            employee = self._require_payroll_eligible_employee(command.employee_id)
            self._validate_command(command)
            neto = float(command.neto if command.neto is not None else command.total)
            total = float(command.total)

            existing = self.payroll_repository.get_payment_by_operation_id(op_id)
            if existing:
                return PayrollApplicationResult(
                    ok=True,
                    payroll_payment_id=existing.id,
                    employee_id=existing.empleado_id,
                    total=existing.total,
                    neto=existing.total,
                    operation_id=op_id,
                    created=False,
                )

            payment_id = self.payroll_repository.create_payment(
                {
                    "empleado_id": command.employee_id,
                    "periodo_inicio": command.period_start,
                    "periodo_fin": command.period_end,
                    "salario_base": command.salario_base,
                    "bonos": command.bonos,
                    "deducciones": command.deducciones,
                    "total": total,
                    "metodo_pago": command.metodo_pago,
                    "estado": "pagado",
                    "usuario": command.usuario,
                    "operation_id": op_id,
                    "source_module": "rrhh",
                    "source_id": command.source_id,
                }
            )

            nombre = employee.nombre_completo
            self.event_publisher.publish(
                PayrollGeneratedPayload(
                    operation_id=op_id,
                    employee_id=command.employee_id,
                    period_start=command.period_start,
                    period_end=command.period_end,
                    total=total,
                    neto=neto,
                    sucursal_id=command.sucursal_id,
                    nombre=nombre,
                    payroll_payment_id=payment_id,
                )
            )
            self.event_publisher.publish(
                PayrollPaidPayload(
                    operation_id=op_id,
                    payroll_payment_id=payment_id,
                    employee_id=command.employee_id,
                    period_start=command.period_start,
                    period_end=command.period_end,
                    total=total,
                    neto=neto,
                    metodo_pago=command.metodo_pago,
                    sucursal_id=command.sucursal_id,
                    nombre=nombre,
                    source_module="rrhh",
                    source_id=command.source_id,
                )
            )
            return PayrollApplicationResult(
                ok=True,
                payroll_payment_id=payment_id,
                employee_id=command.employee_id,
                total=total,
                neto=neto,
                operation_id=op_id,
                created=True,
            )
        except Exception as exc:
            return PayrollApplicationResult(
                ok=False,
                payroll_payment_id=0,
                employee_id=command.employee_id,
                total=float(command.total or 0),
                neto=float(command.neto if command.neto is not None else command.total or 0),
                operation_id=op_id,
                created=False,
                error=str(exc),
            )

    def _require_payroll_eligible_employee(self, employee_id: int) -> Employee:
        self._ensure_positive_int(employee_id, "employee_id")
        employee = self.employee_repository.get_by_id(employee_id)
        if not employee:
            raise ValueError(f"Empleado no encontrado: {employee_id}")
        if not self.eligibility_policy.is_payroll_eligible(employee):
            raise ValueError(f"Empleado no elegible para nómina: {employee_id}")
        return employee

    def _validate_command(self, command: PayrollPaymentCommand) -> None:
        self._ensure_text(command.period_start, "period_start")
        self._ensure_text(command.period_end, "period_end")
        self._ensure_text(command.metodo_pago, "metodo_pago")
        self._ensure_positive_int(command.sucursal_id, "sucursal_id")
        if command.total < 0:
            raise ValueError("total no puede ser negativo")
        if command.neto is not None and command.neto < 0:
            raise ValueError("neto no puede ser negativo")

    @staticmethod
    def _ensure_positive_int(value: int, field_name: str) -> None:
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"{field_name} debe ser un entero positivo")

    @staticmethod
    def _ensure_text(value: str, field_name: str) -> None:
        if not str(value or "").strip():
            raise ValueError(f"{field_name} es obligatorio")


class EmployeeIdentityApplicationService:
    """Consolidates labor identity links between employees, users and drivers.

    Phase 9 keeps the links additive and nullable: it never creates duplicate
    employees, users or drivers; it only links existing records to the canonical
    ``personal`` employee row after validating that employee is active.
    """

    def __init__(
        self,
        repository: EmployeeIdentityRepository,
        eligibility_policy: Optional[EmployeeEligibilityPolicy] = None,
        event_publisher: Optional[RRHHEventPublisher] = None,
    ):
        self.repository = repository
        self.eligibility_policy = eligibility_policy or EmployeeEligibilityPolicy()
        self.event_publisher = event_publisher or RRHHEventPublisher()

    def link_user_to_employee(
        self,
        user_id: int,
        employee_id: int,
        operation_id: Optional[str] = None,
    ) -> int:
        employee = self._require_active_employee(employee_id)
        self._ensure_positive(user_id, "user_id")
        if not self.repository.user_exists(user_id):
            raise ValueError(f"Usuario no encontrado: {user_id}")

        current_employee_id = self.repository.get_user_employee_id(user_id)
        if current_employee_id == employee_id:
            return employee_id
        if current_employee_id:
            raise ValueError(
                f"El usuario {user_id} ya está vinculado al empleado {current_employee_id}"
            )
        existing_user_id = self.repository.get_user_id_for_employee(employee_id)
        if existing_user_id and existing_user_id != user_id:
            raise ValueError(
                f"El empleado {employee_id} ya está vinculado al usuario {existing_user_id}"
            )

        self.repository.link_user_to_employee(user_id, employee_id)
        self.event_publisher.publish(
            EmployeeEventPayload(
                operation_id=operation_id or new_operation_id("usuario-empleado"),
                employee_id=employee_id,
                nombre=employee.nombre_completo,
                puesto=employee.puesto,
                sucursal_id=employee.sucursal_id,
                changes={"usuario_id": user_id, "identity_link": "usuario"},
            )
        )
        return employee_id

    def link_driver_to_employee(
        self,
        driver_id: int,
        employee_id: int,
        operation_id: Optional[str] = None,
    ) -> int:
        self._require_active_employee(employee_id)
        self._ensure_positive(driver_id, "driver_id")
        if not self.repository.driver_exists(driver_id):
            raise ValueError(f"Repartidor no encontrado: {driver_id}")

        current_employee_id = self.repository.get_driver_employee_id(driver_id)
        if current_employee_id == employee_id:
            return employee_id
        if current_employee_id:
            raise ValueError(
                f"El repartidor {driver_id} ya está vinculado al empleado {current_employee_id}"
            )
        existing_driver_id = self.repository.get_driver_id_for_employee(employee_id)
        if existing_driver_id and existing_driver_id != driver_id:
            raise ValueError(
                f"El empleado {employee_id} ya está vinculado al repartidor {existing_driver_id}"
            )

        self.repository.link_driver_to_employee(driver_id, employee_id)
        self.event_publisher.publish(
            DriverAssignedPayload(
                operation_id=operation_id or new_operation_id("repartidor-empleado"),
                driver_id=driver_id,
                employee_id=employee_id,
                source_module="rrhh",
                reason="identity_link",
            )
        )
        return employee_id

    def _require_active_employee(self, employee_id: int) -> Employee:
        self._ensure_positive(employee_id, "employee_id")
        employee = self.repository.get_employee(employee_id)
        if not employee:
            raise ValueError(f"Empleado no encontrado: {employee_id}")
        if not self.eligibility_policy.is_active(employee):
            raise ValueError(f"Empleado inactivo no puede vincularse: {employee_id}")
        return employee

    @staticmethod
    def _ensure_positive(value: int, field_name: str) -> None:
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"{field_name} debe ser un entero positivo")


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
            return str(role_id)
        return self.repository.create_role(data)

    def deactivate_role(self, role_id: int) -> None:
        self.repository.deactivate_role(role_id)

    def list_assignments(self, active_only: bool = True) -> List[ShiftAssignment]:
        return self.repository.list_assignments(active_only=active_only)

    def save_assignment(self, data: Dict[str, Any], assignment_id: Optional[int] = None) -> int:
        if assignment_id:
            self.repository.update_assignment(assignment_id, data)
            return str(assignment_id)
        return self.repository.create_assignment(data)

    def deactivate_assignment(self, assignment_id: int) -> None:
        self.repository.deactivate_assignment(assignment_id)
