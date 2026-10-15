"""Employee use cases — create, update, deactivate, link user, catalogs.

Auditoría RRHH cebf67a: cada comando exige su permiso ``RRHH.*`` y opera sólo
sobre empleados de una sucursal al alcance del actor (HR-01/HR-02). La edición
aplica las mismas invariantes que el alta y el salario cambia con VIGENCIA
(historial), no reescribiendo el pasado (HR-09/HR-23).
"""

from __future__ import annotations

import json
from datetime import date

from backend.application.use_cases.hr.hr_result import HRResult
from backend.domain.hr.entities import Department, Employee, Position
from backend.domain.hr.enums import ContractType, PaymentFrequency
from backend.domain.hr.exceptions import HRDomainError
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy, HRPermission
from backend.domain.hr.value_objects import Email, Money, PhoneE164
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

#: Campos sensibles cuyo valor no se escribe completo en la bitácora.
_MASKED_FIELDS = frozenset({"bank_account_reference", "tax_identifier"})


def _validate_contact(phone: str | None, email: str | None) -> None:
    if phone:
        PhoneE164(phone)  # raises HRDomainError if invalid
    if email:
        Email(email)


def _mask(field: str, value) -> str:
    text = "" if value is None else str(value)
    if field in _MASKED_FIELDS and len(text) > 4:
        return "•" * (len(text) - 4) + text[-4:]
    return text


class CreateEmployeeUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, employee_code: str,
                first_name: str, last_name: str, branch_id: str, contract_type: str,
                payment_frequency: str, base_salary: str, daily_salary: str,
                hire_date: date, operation_id: str, currency_code: str = "MXN",
                phone_e164: str | None = None, email: str | None = None,
                department_id: str | None = None, position_id: str | None = None,
                supervisor_employee_id: str | None = None,
                tax_identifier: str | None = None,
                bank_account_reference: str | None = None,
                emergency_contact_name: str | None = None,
                emergency_contact_phone: str | None = None,
                link_user_id: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.EMPLOYEE_CREATE)
        self._auth.require_branch(actor_user_id, branch_id)
        try:
            _validate_contact(phone_e164, email)
            employee = Employee.create(
                employee_code, first_name, last_name, branch_id,
                ContractType(contract_type), PaymentFrequency(payment_frequency),
                Money.from_string(base_salary, currency_code),
                Money.from_string(daily_salary, currency_code), hire_date,
                phone_e164=phone_e164, email=email, department_id=department_id,
                position_id=position_id, supervisor_employee_id=supervisor_employee_id,
                tax_identifier=tax_identifier,
                bank_account_reference=bank_account_reference,
                emergency_contact_name=emergency_contact_name,
                emergency_contact_phone=emergency_contact_phone)
        except (HRDomainError, ValueError) as exc:
            return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)

        with HRUnitOfWork(connection) as uow:
            if uow.employees.get_by_code(employee_code):
                return HRResult.fail(
                    f"Ya existe un empleado con código {employee_code}",
                    "DUPLICATE_CODE", operation_id=operation_id)
            uow.employees.save(employee)
            uow.salary_history.record(
                employee_id=employee.id, daily_salary=employee.daily_salary,
                base_salary=employee.base_salary, effective_from=hire_date,
                reason="Alta", changed_by_user_id=actor_user_id, operation_id=operation_id)
            if link_user_id:
                uow.employees.link_user(link_user_id, employee.id)
            uow.audit.record(action="EMPLOYEE_CREATED", actor_user_id=actor_user_id,
                             entity_type="employee", entity_id=employee.id,
                             detail=f"code={employee_code}", operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.EMPLOYEE_CREATED.value,
                               json.dumps({"employee_id": employee.id,
                                           "employee_code": employee_code,
                                           "operation_id": operation_id}), operation_id)
        return HRResult.ok("Empleado creado", entity_id=employee.id,
                           operation_id=operation_id)


class UpdateEmployeeUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, employee_id: str,
                operation_id: str, salary_effective_from: date | None = None,
                salary_change_reason: str = "", **fields) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.EMPLOYEE_UPDATE)
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get(employee_id)
            if employee is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, employee.branch_id)
            try:
                _validate_contact(fields.get("phone_e164"), fields.get("email"))
                changes = employee.update_profile(**fields)
                salary_changed = False
                if "daily_salary" in fields or "base_salary" in fields:
                    currency = employee.daily_salary.currency_code
                    daily = Money.from_string(
                        fields.get("daily_salary", employee.daily_salary.to_string()), currency)
                    base = Money.from_string(
                        fields.get("base_salary", employee.base_salary.to_string()), currency)
                    if (daily.amount != employee.daily_salary.amount
                            or base.amount != employee.base_salary.amount):
                        effective = salary_effective_from or date.today()
                        if effective < employee.hire_date:
                            raise HRDomainError(
                                "La vigencia del salario no puede ser anterior al ingreso")
                        changes["daily_salary"] = (employee.daily_salary.to_string(),
                                                   daily.to_string())
                        changes["base_salary"] = (employee.base_salary.to_string(),
                                                  base.to_string())
                        employee.change_salary(daily_salary=daily, base_salary=base)
                        uow.salary_history.record(
                            employee_id=employee.id, daily_salary=daily, base_salary=base,
                            effective_from=effective,
                            reason=salary_change_reason.strip() or "Cambio de salario",
                            changed_by_user_id=actor_user_id, operation_id=operation_id)
                        salary_changed = True
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            if not changes:
                return HRResult.ok("Sin cambios", entity_id=employee_id,
                                   operation_id=operation_id)
            uow.employees.update(employee)
            detail = json.dumps({key: [_mask(key, before), _mask(key, after)]
                                 for key, (before, after) in changes.items()},
                                ensure_ascii=False)
            uow.audit.record(action="EMPLOYEE_UPDATED", actor_user_id=actor_user_id,
                             entity_type="employee", entity_id=employee.id,
                             detail=detail, operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.EMPLOYEE_UPDATED.value,
                               json.dumps({"employee_id": employee.id,
                                           "salary_changed": salary_changed,
                                           "operation_id": operation_id}), operation_id)
        return HRResult.ok("Empleado actualizado", entity_id=employee_id,
                           operation_id=operation_id)


class DeactivateEmployeeUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, employee_id: str,
                termination_date: date, reason: str, operation_id: str) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.EMPLOYEE_DEACTIVATE)
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get(employee_id)
            if employee is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, employee.branch_id)
            try:
                if termination_date < employee.hire_date:
                    raise HRDomainError("La baja no puede ser anterior al ingreso")
                employee.deactivate(termination_date=termination_date, reason=reason)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.employees.update(employee)
            uow.audit.record(action="EMPLOYEE_DEACTIVATED", actor_user_id=actor_user_id,
                             entity_type="employee", entity_id=employee.id,
                             detail=reason, operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.EMPLOYEE_DEACTIVATED.value,
                               json.dumps({"employee_id": employee.id,
                                           "operation_id": operation_id}), operation_id)
        return HRResult.ok("Empleado dado de baja", entity_id=employee_id,
                           operation_id=operation_id)


class LinkEmployeeUserUseCase:
    """Vincula un usuario del sistema con su empleado (HR-30) — la pieza que
    hace que la apertura de caja de ese usuario se convierta en asistencia.
    Al vincular se reprocesan los eventos de caja que esperaban este vínculo
    (HR-06), una sola vez cada uno."""

    def __init__(self, authorization: AuthorizationPolicy | None = None,
                 *, reprocess=None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._reprocess = reprocess

    def execute(self, connection, *, actor_user_id: str, employee_id: str, user_id: str,
                operation_id: str) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.EMPLOYEE_UPDATE)
        user_id = str(user_id or "").strip()
        if not user_id:
            return HRResult.fail("Seleccione el usuario a vincular", "VALIDATION",
                                 operation_id=operation_id)
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get(employee_id)
            if employee is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, employee.branch_id)
            exists = connection.execute(
                "SELECT personal_id FROM usuarios WHERE id=?", (user_id,)).fetchone()
            if exists is None:
                return HRResult.fail("El usuario no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            if exists[0] and str(exists[0]) != employee_id:
                return HRResult.fail("El usuario ya está vinculado con otro empleado",
                                     "ALREADY_LINKED", operation_id=operation_id)
            current = uow.employees.user_for_employee(employee_id)
            if current and current != user_id:
                return HRResult.fail("El empleado ya está vinculado con otro usuario",
                                     "ALREADY_LINKED", operation_id=operation_id)
            uow.employees.link_user(user_id, employee_id)
            uow.audit.record(action="EMPLOYEE_USER_LINKED", actor_user_id=actor_user_id,
                             entity_type="employee", entity_id=employee_id,
                             detail=f"user={user_id}", operation_id=operation_id)
        reprocessed = 0
        if self._reprocess is not None:
            reprocessed = self._reprocess(connection, user_id=user_id)
        message = "Usuario vinculado"
        if reprocessed:
            message += f"; se aplicaron {reprocessed} marcación(es) de caja pendientes"
        return HRResult.ok(message, entity_id=employee_id, operation_id=operation_id,
                           reprocessed=reprocessed)


class ManageCatalogUseCase:
    """Create departments/positions (settings). Requires RRHH.configuracion.gestionar."""

    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def create_department(self, connection, *, actor_user_id: str, code: str, name: str,
                          branch_id: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.SETTINGS_MANAGE)
        try:
            department = Department.create(code, name, branch_id=branch_id)
        except HRDomainError as exc:
            return HRResult.fail(str(exc), "VALIDATION")
        with HRUnitOfWork(connection) as uow:
            uow.departments.save(department)
            uow.audit.record(action="DEPARTMENT_CREATED", actor_user_id=actor_user_id,
                             entity_type="department", entity_id=department.id,
                             detail=f"{code} {name}")
        return HRResult.ok("Departamento creado", entity_id=department.id)

    def create_position(self, connection, *, actor_user_id: str, code: str, name: str,
                        department_id: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.SETTINGS_MANAGE)
        try:
            position = Position.create(code, name, department_id=department_id)
        except HRDomainError as exc:
            return HRResult.fail(str(exc), "VALIDATION")
        with HRUnitOfWork(connection) as uow:
            uow.positions.save(position)
            uow.audit.record(action="POSITION_CREATED", actor_user_id=actor_user_id,
                             entity_type="position", entity_id=position.id,
                             detail=f"{code} {name}")
        return HRResult.ok("Puesto creado", entity_id=position.id)

    def update_item(self, connection, *, actor_user_id: str, kind: str, item_id: str,
                    name: str, active: bool = True) -> HRResult:
        """Renombrar o desactivar un departamento/puesto (HR-30). No se borra: los
        empleados que lo tienen conservan la referencia."""
        from backend.infrastructure.db.repositories.hr.employee_repository import (
            update_catalog,
        )
        self._auth.require(actor_user_id, HRPermission.SETTINGS_MANAGE)
        table = {"department": "hr_departments", "position": "hr_positions"}.get(kind)
        if table is None:
            return HRResult.fail("Catálogo desconocido", "VALIDATION")
        if not str(name or "").strip():
            return HRResult.fail("El nombre es obligatorio", "VALIDATION")
        with HRUnitOfWork(connection) as uow:
            repo = uow.departments if kind == "department" else uow.positions
            if repo.get(item_id) is None:
                return HRResult.fail("El elemento no existe", "NOT_FOUND")
            update_catalog(repo, table, item_id, name=name.strip(), active=active)
            uow.audit.record(action="CATALOG_UPDATED", actor_user_id=actor_user_id,
                             entity_type=kind, entity_id=item_id,
                             detail=f"{name.strip()} activo={active}")
        return HRResult.ok("Catálogo actualizado", entity_id=item_id)
