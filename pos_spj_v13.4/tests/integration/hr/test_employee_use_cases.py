"""FASE 3 — employee use cases: create, update, deactivate, link user, permissions."""

from datetime import date

import pytest

from backend.application.use_cases.hr.employee_use_cases import (
    CreateEmployeeUseCase,
    DeactivateEmployeeUseCase,
    ManageCatalogUseCase,
    UpdateEmployeeUseCase,
)
from backend.domain.hr.exceptions import PermissionDeniedError
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.ids import new_uuid

BRANCH = new_uuid()


class _Checker:
    def __init__(self, granted: set[str]) -> None:
        self._granted = granted

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return permission_code in self._granted


def _create(conn, **overrides):
    payload = dict(actor_user_id=new_uuid(), employee_code="EMP-100",
                   first_name="Ana", last_name="García", branch_id=BRANCH,
                   contract_type="PERMANENT", payment_frequency="SEMIMONTHLY",
                   base_salary="15000.00", daily_salary="500.00",
                   hire_date=date(2025, 1, 1), operation_id=new_uuid())
    payload.update(overrides)
    return CreateEmployeeUseCase().execute(conn, **payload)


class TestCreateEmployee:
    def test_creates_with_uuid_and_audit(self, hr_conn):
        result = _create(hr_conn)
        assert result.success and result.entity_id
        audit = hr_conn.execute(
            "SELECT COUNT(*) FROM hr_audit_log WHERE action='EMPLOYEE_CREATED'").fetchone()[0]
        assert audit == 1
        events = hr_conn.execute(
            "SELECT COUNT(*) FROM hr_outbox WHERE event_name='EMPLOYEE_CREATED'").fetchone()[0]
        assert events == 1

    def test_duplicate_code_rejected(self, hr_conn):
        _create(hr_conn)
        result = _create(hr_conn, operation_id=new_uuid())
        assert not result.success and result.error_code == "DUPLICATE_CODE"

    def test_invalid_phone_rejected(self, hr_conn):
        result = _create(hr_conn, phone_e164="5512345678")
        assert not result.success and result.error_code == "VALIDATION"

    def test_links_user(self, hr_conn):
        user_id = new_uuid()
        hr_conn.execute("INSERT INTO usuarios (id, usuario) VALUES (?, 'ana')", (user_id,))
        result = _create(hr_conn, link_user_id=user_id)
        with HRUnitOfWork(hr_conn) as uow:
            linked = uow.employees.get_by_user_id(user_id)
        assert linked is not None and linked.id == result.entity_id

    def test_permission_enforced(self, hr_conn):
        auth = AuthorizationPolicy(_Checker(set()))
        with pytest.raises(PermissionDeniedError):
            CreateEmployeeUseCase(auth).execute(
                hr_conn, actor_user_id=new_uuid(), employee_code="X", first_name="A",
                last_name="B", branch_id=BRANCH, contract_type="PERMANENT",
                payment_frequency="MONTHLY", base_salary="1", daily_salary="1",
                hire_date=date(2025, 1, 1), operation_id=new_uuid())

    def test_permission_granted_allows(self, hr_conn):
        auth = AuthorizationPolicy(_Checker({"hr.employee.create"}))
        result = CreateEmployeeUseCase(auth).execute(
            hr_conn, actor_user_id=new_uuid(), employee_code="OK", first_name="A",
            last_name="B", branch_id=BRANCH, contract_type="PERMANENT",
            payment_frequency="MONTHLY", base_salary="1", daily_salary="1",
            hire_date=date(2025, 1, 1), operation_id=new_uuid())
        assert result.success


class TestUpdateDeactivate:
    def test_update_salary(self, hr_conn):
        created = _create(hr_conn)
        result = UpdateEmployeeUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=created.entity_id,
            operation_id=new_uuid(), base_salary="16000.00")
        assert result.success
        with HRUnitOfWork(hr_conn) as uow:
            assert uow.employees.get(created.entity_id).base_salary.to_string() == "16000.00"

    def test_deactivate_requires_reason(self, hr_conn):
        created = _create(hr_conn)
        result = DeactivateEmployeeUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=created.entity_id,
            termination_date=date(2026, 7, 16), reason="", operation_id=new_uuid())
        assert not result.success

    def test_deactivate_ok(self, hr_conn):
        created = _create(hr_conn)
        result = DeactivateEmployeeUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=created.entity_id,
            termination_date=date(2026, 7, 16), reason="renuncia", operation_id=new_uuid())
        assert result.success
        with HRUnitOfWork(hr_conn) as uow:
            assert not uow.employees.get(created.entity_id).active


class TestCatalogs:
    def test_create_department_and_position(self, hr_conn):
        uc = ManageCatalogUseCase()
        dept = uc.create_department(hr_conn, actor_user_id=new_uuid(), code="VENTAS",
                                    name="Ventas")
        assert dept.success
        pos = uc.create_position(hr_conn, actor_user_id=new_uuid(), code="CAJ",
                                 name="Cajero", department_id=dept.entity_id)
        assert pos.success
