"""Employee use cases — create, update, deactivate, link user, catalogs."""

from __future__ import annotations

import json
from datetime import date

from backend.application.use_cases.hr.hr_result import HRResult
from backend.domain.hr.entities import Department, Employee, Position
from backend.domain.hr.enums import ContractType, PaymentFrequency
from backend.domain.hr.exceptions import (
    DuplicateEmployeeCodeError,
    EmployeeNotFoundError,
    HRDomainError,
)
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy
from backend.domain.hr.value_objects import Email, Money, PhoneE164
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


def _validate_contact(phone: str | None, email: str | None) -> None:
    if phone:
        PhoneE164(phone)  # raises HRDomainError if invalid
    if email:
        Email(email)


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
        self._auth.require(actor_user_id, "hr.employee.create")
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
        except HRDomainError as exc:
            return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)

        with HRUnitOfWork(connection) as uow:
            if uow.employees.get_by_code(employee_code):
                return HRResult.fail(
                    f"Ya existe un empleado con código {employee_code}",
                    "DUPLICATE_CODE", operation_id=operation_id)
            uow.employees.save(employee)
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
                operation_id: str, **fields) -> HRResult:
        self._auth.require(actor_user_id, "hr.employee.update")
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get(employee_id)
            if employee is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            try:
                _validate_contact(fields.get("phone_e164"), fields.get("email"))
                for key in ("first_name", "last_name", "phone_e164", "email",
                            "department_id", "position_id", "supervisor_employee_id",
                            "bank_account_reference", "tax_identifier",
                            "emergency_contact_name", "emergency_contact_phone"):
                    if key in fields and fields[key] is not None:
                        setattr(employee, key, fields[key])
                if "base_salary" in fields:
                    employee.base_salary = Money.from_string(fields["base_salary"])
                if "daily_salary" in fields:
                    employee.daily_salary = Money.from_string(fields["daily_salary"])
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            employee.touch()
            uow.employees.update(employee)
            uow.audit.record(action="EMPLOYEE_UPDATED", actor_user_id=actor_user_id,
                             entity_type="employee", entity_id=employee.id,
                             detail="update", operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.EMPLOYEE_UPDATED.value,
                               json.dumps({"employee_id": employee.id,
                                           "operation_id": operation_id}), operation_id)
        return HRResult.ok("Empleado actualizado", entity_id=employee_id,
                           operation_id=operation_id)


class DeactivateEmployeeUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, employee_id: str,
                termination_date: date, reason: str, operation_id: str) -> HRResult:
        self._auth.require(actor_user_id, "hr.employee.deactivate")
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get(employee_id)
            if employee is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            try:
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


class ManageCatalogUseCase:
    """Create departments/positions (settings). Requires hr.settings.manage."""

    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def create_department(self, connection, *, actor_user_id: str, code: str, name: str,
                          branch_id: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, "hr.settings.manage")
        try:
            department = Department.create(code, name, branch_id=branch_id)
        except HRDomainError as exc:
            return HRResult.fail(str(exc), "VALIDATION")
        with HRUnitOfWork(connection) as uow:
            uow.departments.save(department)
        return HRResult.ok("Departamento creado", entity_id=department.id)

    def create_position(self, connection, *, actor_user_id: str, code: str, name: str,
                        department_id: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, "hr.settings.manage")
        try:
            position = Position.create(code, name, department_id=department_id)
        except HRDomainError as exc:
            return HRResult.fail(str(exc), "VALIDATION")
        with HRUnitOfWork(connection) as uow:
            uow.positions.save(position)
        return HRResult.ok("Puesto creado", entity_id=position.id)
