"""Composition root for the HR desktop module.

The ONLY place that touches the database connection to wire query services and
use cases. The view and pages never see the connection nor the AppContainer.

Auditoría RRHH cebf67a HR-01: los 13 casos de uso se construían SIN verificador
de permisos — con una sesión sin permisos se daba de alta un empleado y el actor
quedaba como "desktop". Ahora todos comparten una política ligada a la sesión
viva (``HRSessionPermissionChecker``) que falla cerrada.
"""

from __future__ import annotations

from datetime import datetime

from backend.application.event_handlers.hr.cash_attendance_handlers import (
    reprocess_pending_cash_attendance,
)
from backend.application.hr.business_clock import branch_now
from backend.application.hr.payroll_receipts import (
    ExportPayrollReceiptsPdfUseCase,
    PrintPayrollReceiptTicketUseCase,
)
from backend.application.use_cases.hr.payroll_adjustment_use_cases import (
    GenerateComplementaryPayrollRunUseCase,
    ReversePayrollPaymentUseCase,
)
from backend.application.use_cases.hr.payroll_inputs_use_cases import (
    CapturePayrollInputUseCase,
    GrantEmployeeLoanUseCase,
    ResolvePayrollInputUseCase,
)
from backend.application.use_cases.hr.time_clock_use_cases import (
    EnrollCredentialUseCase,
    ImportTimeClockFileUseCase,
    KioskPunchUseCase,
    RegisterTimeClockDeviceUseCase,
    RevokeCredentialUseCase,
    SyncTimeClockDeviceUseCase,
)
from backend.infrastructure.hardware.payroll_receipt_printer import PayrollReceiptPrinter
from backend.infrastructure.hr.payroll_receipt_renderers import render_payroll_receipts_pdf
from backend.infrastructure.hr.time_clock_drivers import (
    TIME_CLOCK_DRIVERS,
    parse_attendance_file,
)
from backend.application.hr.session_authorization import (
    HRSessionPermissionChecker,
    session_branch_id,
)
from backend.application.queries.hr.hr_query_services import (
    AttendanceQueryService,
    HROperationsQueryService,
    EmployeeQueryService,
    HRDashboardQueryService,
    LeaveQueryService,
    PayrollQueryService,
    ShiftQueryService,
)
from backend.application.use_cases.hr.attendance_use_cases import (
    ApproveAttendanceAdjustmentUseCase,
    RegisterManualAttendanceUseCase,
    RequestAttendanceAdjustmentUseCase,
)
from backend.application.use_cases.hr.employee_use_cases import (
    CreateEmployeeUseCase,
    DeactivateEmployeeUseCase,
    LinkEmployeeUserUseCase,
    ManageCatalogUseCase,
    UpdateEmployeeUseCase,
)
from backend.application.use_cases.hr.leave_use_cases import (
    AdjustLeaveBalanceUseCase,
    ApproveLeaveUseCase,
    CancelLeaveUseCase,
    RequestLeaveUseCase,
    VacationBalanceQuery,
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
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from frontend.desktop.modules.hr.hr_presenter import HRPresenter


def build_hr_presenter(connection, session_context=None, *,
                       authorization: AuthorizationPolicy | None = None) -> HRPresenter:
    # Idempotent bootstrap (the schema DDL uses IF NOT EXISTS internally);
    # guarantees the tables exist even on a dev DB opened before migration 118 ran.
    create_hr_schema(connection)
    auth = authorization or AuthorizationPolicy(HRSessionPermissionChecker(session_context))

    query_services = {
        "dashboard": HRDashboardQueryService(connection),
        "employees": EmployeeQueryService(connection),
        "attendance": AttendanceQueryService(connection),
        "shifts": ShiftQueryService(connection),
        "leave": LeaveQueryService(connection),
        "payroll": PayrollQueryService(connection),
        "vacation_balance": VacationBalanceQuery(),
        "operations": HROperationsQueryService(connection),
    }
    use_cases = {
        "create_employee": CreateEmployeeUseCase(auth),
        "update_employee": UpdateEmployeeUseCase(auth),
        "deactivate_employee": DeactivateEmployeeUseCase(auth),
        "link_user": LinkEmployeeUserUseCase(
            auth, reprocess=lambda conn, user_id: reprocess_pending_cash_attendance(
                conn, user_id=user_id)),
        "catalog": ManageCatalogUseCase(auth),
        "manual_attendance": RegisterManualAttendanceUseCase(auth),
        "request_adjustment": RequestAttendanceAdjustmentUseCase(auth),
        "approve_adjustment": ApproveAttendanceAdjustmentUseCase(auth),
        "create_shift": CreateShiftUseCase(auth),
        "assign_shift": AssignShiftUseCase(auth),
        "request_leave": RequestLeaveUseCase(auth),
        "approve_leave": ApproveLeaveUseCase(auth),
        "cancel_leave": CancelLeaveUseCase(auth),
        "generate_payroll": GeneratePayrollRunUseCase(auth),
        "authorize_payroll": AuthorizePayrollRunUseCase(auth),
        "pay_payroll": PayPayrollRunUseCase(auth),
        "cancel_payroll": CancelPayrollRunUseCase(auth),
        "complementary_payroll": GenerateComplementaryPayrollRunUseCase(auth),
        "reverse_payment": ReversePayrollPaymentUseCase(auth),
        "receipts_pdf": ExportPayrollReceiptsPdfUseCase(auth, renderer=render_payroll_receipts_pdf),
        "receipts_ticket": PrintPayrollReceiptTicketUseCase(
            auth, printer=PayrollReceiptPrinter(connection)),
        "capture_input": CapturePayrollInputUseCase(auth),
        "resolve_input": ResolvePayrollInputUseCase(auth),
        "grant_loan": GrantEmployeeLoanUseCase(auth),
        "adjust_leave_balance": AdjustLeaveBalanceUseCase(auth),
        "register_device": RegisterTimeClockDeviceUseCase(auth),
        "enroll_credential": EnrollCredentialUseCase(auth),
        "revoke_credential": RevokeCredentialUseCase(auth),
        "kiosk_punch": KioskPunchUseCase(auth),
        "sync_device": SyncTimeClockDeviceUseCase(auth, drivers=TIME_CLOCK_DRIVERS),
        "import_device_file": ImportTimeClockFileUseCase(auth, parser=parse_attendance_file),
        "dispatch_outbox": lambda: _dispatch_hr_outbox(connection),
    }

    def business_now() -> datetime:
        """HR-22/HR-24: "hoy" es el de la sucursal, no el del equipo."""
        return branch_now(connection, session_branch_id(session_context))

    return HRPresenter(
        connection_provider=lambda: connection,
        query_services=query_services,
        use_cases=use_cases,
        session_context=session_context,
        authorization=auth,
        clock=business_now,
    )


def _dispatch_hr_outbox(connection) -> dict:
    from backend.application.use_cases.hr.finance_wiring import dispatch_hr_outbox
    from backend.shared.events.application_bus import get_bus
    return dispatch_hr_outbox(connection, get_bus())


def create_hr_view(container, parent=None):
    """Factory used by navigation. Extracts only what the module needs."""
    from frontend.desktop.modules.hr.hr_view import HRView

    connection = getattr(container, "db", None) or getattr(container, "db_conn", None)
    session_context = getattr(container, "session_context", None)
    presenter = build_hr_presenter(connection, session_context)
    return HRView(presenter, parent)

