"""Composition root for the HR desktop module.

The ONLY place that touches the database connection to wire query services and
use cases. The view and pages never see the connection nor the AppContainer.
"""

from __future__ import annotations

from backend.application.queries.hr.hr_query_services import (
    AttendanceQueryService,
    EmployeeQueryService,
    HRDashboardQueryService,
    LeaveQueryService,
    PayrollQueryService,
    ShiftQueryService,
)
from backend.application.use_cases.hr.attendance_use_cases import (
    ApproveAttendanceAdjustmentUseCase,
    RegisterManualAttendanceUseCase,
)
from backend.application.use_cases.hr.employee_use_cases import (
    CreateEmployeeUseCase,
    DeactivateEmployeeUseCase,
    ManageCatalogUseCase,
)
from backend.application.use_cases.hr.leave_use_cases import (
    ApproveLeaveUseCase,
    RequestLeaveUseCase,
)
from backend.application.use_cases.hr.payroll_use_cases import (
    AuthorizePayrollRunUseCase,
    CancelPayrollRunUseCase,
    GeneratePayrollRunUseCase,
    PayPayrollRunUseCase,
)
from backend.application.use_cases.hr.shift_use_cases import (
    AssignShiftUseCase,
    CreateShiftUseCase,
)
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from frontend.desktop.modules.hr.hr_presenter import HRPresenter


def build_hr_presenter(connection, session_context=None) -> HRPresenter:
    # Idempotent bootstrap (the schema DDL uses IF NOT EXISTS internally);
    # guarantees the tables exist even on a dev DB opened before migration 118 ran.
    create_hr_schema(connection)

    query_services = {
        "dashboard": HRDashboardQueryService(connection),
        "employees": EmployeeQueryService(connection),
        "attendance": AttendanceQueryService(connection),
        "shifts": ShiftQueryService(connection),
        "leave": LeaveQueryService(connection),
        "payroll": PayrollQueryService(connection),
    }
    use_cases = {
        "create_employee": CreateEmployeeUseCase(),
        "deactivate_employee": DeactivateEmployeeUseCase(),
        "catalog": ManageCatalogUseCase(),
        "manual_attendance": RegisterManualAttendanceUseCase(),
        "approve_adjustment": ApproveAttendanceAdjustmentUseCase(),
        "create_shift": CreateShiftUseCase(),
        "assign_shift": AssignShiftUseCase(),
        "request_leave": RequestLeaveUseCase(),
        "approve_leave": ApproveLeaveUseCase(),
        "generate_payroll": GeneratePayrollRunUseCase(),
        "authorize_payroll": AuthorizePayrollRunUseCase(),
        "pay_payroll": PayPayrollRunUseCase(),
        "cancel_payroll": CancelPayrollRunUseCase(),
    }
    return HRPresenter(
        connection_provider=lambda: connection,
        query_services=query_services,
        use_cases=use_cases,
        session_context=session_context,
    )


def create_hr_view(container, parent=None):
    """Factory used by navigation. Extracts only what the module needs."""
    from frontend.desktop.modules.hr.hr_view import HRView

    connection = getattr(container, "db", None) or getattr(container, "db_conn", None)
    session_context = getattr(container, "session_context", None)
    presenter = build_hr_presenter(connection, session_context)
    return HRView(presenter, parent)
