"""Leave use cases — request, approve, reject, cancel with validations.

Auditoría RRHH cebf67a:
- HR-02: cada comando opera sólo sobre empleados/solicitudes de una sucursal al
  alcance del actor.
- HR-18: el saldo vacacional es POR CICLO de aniversario con derecho por
  antigüedad (``vacation_balance``), no una cuota fija contra toda la historia.
- HR-19: nadie aprueba su propia ausencia sin ``RRHH.permiso.autoaprobar``; una
  pendiente la cancela quien la pidió o quien aprueba; una APROBADA exige
  ``RRHH.permiso.cancelar_aprobado`` y motivo, publica LEAVE_CANCELLED y, si la
  nómina de esos días ya se autorizó o pagó, lo deja documentado (no la reescribe).
"""

from __future__ import annotations

import json
from datetime import date

from backend.application.hr.leave_balance import LeaveBalanceService
from backend.application.use_cases.hr.hr_result import HRResult
from backend.domain.hr.entities import LeaveRequest
from backend.domain.hr.enums import LeaveStatus, LeaveType
from backend.domain.hr.exceptions import HRDomainError
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy, HRPermission
from backend.domain.hr.policies.leave_policy import LeavePolicy
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class RequestLeaveUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None,
                 *, annual_vacation_days: int | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._policy = LeavePolicy()
        #: ``None`` = tabla por antigüedad; un entero fija los días por ciclo.
        self._annual_days = annual_vacation_days

    def execute(self, connection, *, actor_user_id: str, employee_id: str, branch_id: str,
                leave_type: str, start_date: date, end_date: date, reason: str,
                operation_id: str) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.LEAVE_REQUEST)
        with HRUnitOfWork(connection) as uow:
            if uow.leaves.find_by_operation_id(operation_id):
                return HRResult.ok("Solicitud ya registrada", operation_id=operation_id)
            employee = uow.employees.get(employee_id)
            if employee is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, employee.branch_id)
            if not employee.active:
                return HRResult.fail("El empleado está inactivo", "EMPLOYEE_INACTIVE",
                                     operation_id=operation_id)
            existing = uow.leaves.list_by_employee(employee_id)
            try:
                self._policy.enforce_dates(start_date, end_date)
                if not employee.is_employed_on(start_date):
                    raise HRDomainError("La ausencia empieza fuera de la vigencia del empleado")
                self._policy.enforce_no_overlap(start_date, end_date, existing)
                leave_type_enum = LeaveType(leave_type)
                request = LeaveRequest.create(
                    employee_id, employee.branch_id, leave_type_enum, start_date, end_date,
                    reason, actor_user_id, operation_id)
                if leave_type_enum in self._policy.BALANCE_TYPES:
                    # Libro de saldo: la solicitud APARTA días del ciclo vigente
                    # más antiguo; si no alcanzan, se rechaza aquí.
                    LeaveBalanceService(annual_days=self._annual_days).reserve(
                        uow, employee, request, actor_user_id=actor_user_id)
            except (HRDomainError, ValueError) as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.leaves.save(request)
            uow.audit.record(action="LEAVE_REQUESTED", actor_user_id=actor_user_id,
                             entity_type="leave", entity_id=request.id, detail=leave_type,
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.LEAVE_REQUESTED.value,
                               json.dumps({"leave_id": request.id,
                                           "employee_id": employee_id}), operation_id)
        return HRResult.ok("Solicitud registrada", entity_id=request.id,
                           operation_id=operation_id)


class VacationBalanceQuery:
    """Saldo explicado por el libro de movimientos (pantalla de permisos)."""

    def __init__(self, *, annual_vacation_days: int | None = None) -> None:
        self._annual_days = annual_vacation_days

    def execute(self, connection, *, employee_id: str, on_date: date) -> dict | None:
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get(employee_id)
            if employee is None:
                return None
            balance = LeaveBalanceService(annual_days=self._annual_days).balance(
                uow, employee, on_date)
        return {"available": balance.available, "reserved": balance.reserved,
                "cycles": [{"cycle_start": c.cycle_start.isoformat(),
                            "cycle_end": c.cycle_end.isoformat(),
                            "expires_on": c.expires_on.isoformat(),
                            "remaining": c.remaining} for c in balance.cycles],
                "movements": [dict(m) for m in balance.movements]}


class AdjustLeaveBalanceUseCase:
    """Corrección manual del saldo (días a favor o en contra) con motivo."""

    def __init__(self, authorization: AuthorizationPolicy | None = None, *,
                 annual_vacation_days: int | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._annual_days = annual_vacation_days

    def execute(self, connection, *, actor_user_id: str, employee_id: str, days: int,
                reason: str, on_date: date) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.LEAVE_BALANCE_ADJUST)
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get(employee_id)
            if employee is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND")
            self._auth.require_branch(actor_user_id, employee.branch_id)
            try:
                LeaveBalanceService(annual_days=self._annual_days).adjust(
                    uow, employee, days=int(days), on_date=on_date, reason=reason,
                    actor_user_id=actor_user_id)
            except (HRDomainError, ValueError) as exc:
                return HRResult.fail(str(exc), "VALIDATION")
            uow.audit.record(action="LEAVE_BALANCE_ADJUSTED", actor_user_id=actor_user_id,
                             entity_type="employee", entity_id=employee_id,
                             detail=f"{days} día(s): {reason}")
        return HRResult.ok("Saldo de vacaciones ajustado", entity_id=employee_id)


class ApproveLeaveUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, leave_id: str,
                operation_id: str, approve: bool = True) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.LEAVE_APPROVE)
        with HRUnitOfWork(connection) as uow:
            request = uow.leaves.get(leave_id)
            if request is None:
                return HRResult.fail("La solicitud no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, request.branch_id)
            actor_employee = uow.employees.get_by_user_id(actor_user_id) \
                if _has_users_table(connection) else None
            is_self = actor_employee is not None and actor_employee.id == request.employee_id
            try:
                if approve:
                    request.approve(
                        actor_user_id, is_self=is_self,
                        self_approval_allowed=self._auth.has_permission(
                            actor_user_id, HRPermission.LEAVE_SELF_APPROVE))
                    event = EventName.LEAVE_APPROVED
                else:
                    request.reject(actor_user_id)
                    event = EventName.LEAVE_REJECTED
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.leaves.update(request)
            if request.leave_type is LeaveType.VACATION:
                ledger = LeaveBalanceService()
                if approve:
                    ledger.consume(uow, request, actor_user_id=actor_user_id)
                else:
                    ledger.release(uow, request, actor_user_id=actor_user_id,
                                   reason="Solicitud rechazada")
            uow.audit.record(action=event.value, actor_user_id=actor_user_id,
                             entity_type="leave", entity_id=leave_id, detail="",
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), event.value,
                               json.dumps({"leave_id": leave_id,
                                           "employee_id": request.employee_id}), operation_id)
        return HRResult.ok("Solicitud procesada", entity_id=leave_id,
                           operation_id=operation_id)


class CancelLeaveUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, leave_id: str,
                operation_id: str, reason: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.LEAVE_REQUEST)
        with HRUnitOfWork(connection) as uow:
            request = uow.leaves.get(leave_id)
            if request is None:
                return HRResult.fail("La solicitud no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, request.branch_id)
            was_approved = request.status is LeaveStatus.APPROVED
            if was_approved:
                self._auth.require(actor_user_id, HRPermission.LEAVE_CANCEL_APPROVED)
            elif (actor_user_id != request.requested_by_user_id
                  and not self._auth.has_permission(actor_user_id, HRPermission.LEAVE_APPROVE)):
                return HRResult.fail(
                    "Sólo quien la solicitó o quien aprueba puede cancelar la solicitud",
                    "NOT_OWNER", operation_id=operation_id)
            try:
                request.cancel(actor_user_id, reason=reason)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.leaves.update(request)
            if request.leave_type is LeaveType.VACATION:
                LeaveBalanceService().release(uow, request, actor_user_id=actor_user_id,
                                              reason="Solicitud cancelada")
            affected = _closed_payroll_runs(connection, request) if was_approved else []
            detail = reason or ""
            if affected:
                detail += f" | afecta nómina ya autorizada/pagada: {', '.join(affected)}"
            uow.audit.record(action="LEAVE_CANCELLED", actor_user_id=actor_user_id,
                             entity_type="leave", entity_id=leave_id, detail=detail,
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.LEAVE_CANCELLED.value, json.dumps({
                "leave_id": leave_id, "employee_id": request.employee_id,
                "was_approved": was_approved, "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "affected_payroll_runs": affected}), operation_id)
        message = "Solicitud cancelada"
        if affected:
            message += ("; la nómina de esos días ya estaba autorizada o pagada: "
                        "requiere un ajuste en la siguiente corrida")
        return HRResult.ok(message, entity_id=leave_id, operation_id=operation_id,
                           affected_payroll_runs=affected)


def _has_users_table(connection) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='usuarios'").fetchone() is not None


def _closed_payroll_runs(connection, request: LeaveRequest) -> list[str]:
    rows = connection.execute(
        "SELECT DISTINCT c.payroll_run_id FROM payroll_coverage c JOIN payroll_runs r"
        " ON r.id=c.payroll_run_id WHERE c.employee_id=? AND c.coverage_date BETWEEN ? AND ?"
        " AND r.status IN ('AUTHORIZED','PAID')",
        (request.employee_id, request.start_date.isoformat(),
         request.end_date.isoformat())).fetchall()
    return [str(r[0]) for r in rows]
