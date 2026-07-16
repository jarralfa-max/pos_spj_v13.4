"""Factory classes that wire the canonical HR desktop module."""

from __future__ import annotations

from datetime import date, datetime

from backend.application.commands.attendance_commands import RegisterManualAttendanceCommand
from backend.application.commands.hr_commands import CreateEmployeeCommand, DeactivateEmployeeCommand, UpdateEmployeeCommand
from backend.application.queries.attendance_query_service import AttendanceQueryService
from backend.application.queries.hr_catalog_query_service import HRCatalogQueryService
from backend.application.queries.hr_dashboard_query_service import HRDashboardQueryService
from backend.application.queries.hr_employee_query_service import HREmployeeQueryService
from backend.application.queries.leave_query_service import LeaveQueryService
from backend.application.queries.payroll_query_service import PayrollQueryService
from backend.application.queries.shift_query_service import ShiftQueryService
from backend.application.use_cases.hr import CreateEmployeeUseCase, DeactivateEmployeeUseCase, RegisterManualAttendanceUseCase, UpdateEmployeeUseCase
from backend.domain.hr.enums import ContractType, PaymentFrequency, PunchType
from backend.infrastructure.db.repositories.attendance_repository import SQLiteAttendanceRepository
from backend.infrastructure.db.repositories.employee_repository import SQLiteEmployeeRepository
from backend.shared.ids import new_uuid
from frontend.desktop.modules.hr.hr_presenter_impl import HRDesktopPresenter
from frontend.desktop.modules.hr.hr_view_models import HRAttendanceFormViewModel, HREmployeeFormViewModel


def _connection_from_container(container) -> object:
    return getattr(container, "db", container)


def _session_from_container(container):
    return getattr(container, "session", None)


class _HRActionWiring:
    """Composition root for HR UseCases invoked by the desktop presenter."""

    def __init__(self, connection, session=None) -> None:
        self._connection = connection
        self._session = session
        self._employee_repository = SQLiteEmployeeRepository(connection)
        self._attendance_repository = SQLiteAttendanceRepository(connection)

    def create_employee(self, form: HREmployeeFormViewModel) -> None:
        command = CreateEmployeeCommand(
            operation_id=new_uuid(),
            branch_id=self._branch_id(form),
            user_id=self._user_id(),
            user_name=self._user_name(),
            employee_code=form.employee_code,
            first_name=form.first_name,
            last_name=form.last_name,
            department_id=form.department_id,
            position_id=form.position_id,
            contract_type=self._contract_type(form.contract_type),
            payment_frequency=self._payment_frequency(form.payment_frequency),
            base_salary=form.base_salary,
            daily_salary=form.daily_salary,
            hire_date=form.hire_date,
            phone_e164=form.phone_e164,
            email=form.email,
        )
        CreateEmployeeUseCase(
            self._employee_repository,
            permission_checker=self._has_permission,
        ).execute(command)
        self._commit_if_available()

    def update_employee(self, employee_id: str, form: HREmployeeFormViewModel) -> None:
        command = UpdateEmployeeCommand(
            operation_id=new_uuid(),
            branch_id=self._branch_id(form),
            user_id=self._user_id(),
            user_name=self._user_name(),
            employee_id=employee_id,
            employee_code=form.employee_code,
            first_name=form.first_name,
            last_name=form.last_name,
            department_id=form.department_id,
            position_id=form.position_id,
            contract_type=self._contract_type(form.contract_type),
            payment_frequency=self._payment_frequency(form.payment_frequency),
            base_salary=form.base_salary,
            daily_salary=form.daily_salary,
            hire_date=form.hire_date,
            phone_e164=form.phone_e164,
            email=form.email,
        )
        UpdateEmployeeUseCase(
            self._employee_repository,
            permission_checker=self._has_permission,
        ).execute(command)
        self._commit_if_available()

    def deactivate_employee(self, employee_id: str, reason: str) -> None:
        command = DeactivateEmployeeCommand(
            operation_id=new_uuid(),
            branch_id=str(getattr(self._session, "active_branch_id", "") or getattr(self._session, "sucursal_id", "")),
            user_id=self._user_id(),
            user_name=self._user_name(),
            employee_id=employee_id,
            termination_date=date.today(),
            termination_reason=reason,
        )
        DeactivateEmployeeUseCase(
            self._employee_repository,
            permission_checker=self._has_permission,
        ).execute(command)
        self._commit_if_available()


    def register_manual_attendance(self, form: HRAttendanceFormViewModel) -> None:
        occurred_at = datetime.fromisoformat(form.occurred_at)
        command = RegisterManualAttendanceCommand(
            operation_id=new_uuid(),
            branch_id=form.branch_id,
            user_id=self._user_id(),
            user_name=self._user_name(),
            employee_id=form.employee_id,
            punch_type=PunchType(form.punch_type),
            occurred_at=occurred_at,
            reason=form.reason,
            notes=form.notes,
        )
        RegisterManualAttendanceUseCase(
            self._attendance_repository,
            employee_repository=self._employee_repository,
            permission_checker=self._has_permission,
        ).execute(command)
        self._commit_if_available()

    def _branch_id(self, form: HREmployeeFormViewModel) -> str:
        return form.branch_id or str(getattr(self._session, "active_branch_id", "") or getattr(self._session, "sucursal_id", ""))

    def _user_id(self) -> str:
        return str(getattr(self._session, "user_id", "") or "")

    def _user_name(self) -> str:
        return str(getattr(self._session, "usuario", "") or "")

    def _has_permission(self, _user_id: str | None, permission: str) -> bool:
        if self._session is None or not getattr(self._session, "is_active", False):
            return False
        return bool(self._session.tiene_permiso(permission))

    def _contract_type(self, value: str) -> ContractType:
        return ContractType(str(value).strip().upper())

    def _payment_frequency(self, value: str) -> PaymentFrequency:
        return PaymentFrequency(str(value).strip().upper())

    def _commit_if_available(self) -> None:
        commit = getattr(self._connection, "commit", None)
        if callable(commit):
            commit()


class CanonicalHRModule:
    """HR module entry point used by the main window container wiring."""

    def __new__(cls, container, parent=None):
        from frontend.desktop.modules.hr.hr_view import HRView

        connection = _connection_from_container(container)
        actions = _HRActionWiring(connection, _session_from_container(container))
        presenter = HRDesktopPresenter(
            employee_query_service=HREmployeeQueryService(connection),
            dashboard_query_service=HRDashboardQueryService(connection),
            catalog_query_service=HRCatalogQueryService(connection),
            attendance_query_service=AttendanceQueryService(connection),
            shift_query_service=ShiftQueryService(connection),
            leave_query_service=LeaveQueryService(connection),
            payroll_query_service=PayrollQueryService(connection),
            on_manual_attendance=actions.register_manual_attendance,
            on_create_employee=actions.create_employee,
            on_update_employee=actions.update_employee,
            on_deactivate_employee=actions.deactivate_employee,
        )
        return HRView(presenter, parent)


class CanonicalHRModuleFromConnection:
    """HR module entry point used by the generic module loader."""

    def __new__(cls, connection, _usuario: str | None = None, parent=None):
        from frontend.desktop.modules.hr.hr_view import HRView

        actions = _HRActionWiring(connection)
        presenter = HRDesktopPresenter(
            employee_query_service=HREmployeeQueryService(connection),
            dashboard_query_service=HRDashboardQueryService(connection),
            catalog_query_service=HRCatalogQueryService(connection),
            attendance_query_service=AttendanceQueryService(connection),
            shift_query_service=ShiftQueryService(connection),
            leave_query_service=LeaveQueryService(connection),
            payroll_query_service=PayrollQueryService(connection),
            on_manual_attendance=actions.register_manual_attendance,
            on_create_employee=actions.create_employee,
            on_update_employee=actions.update_employee,
            on_deactivate_employee=actions.deactivate_employee,
        )
        return HRView(presenter, parent)
