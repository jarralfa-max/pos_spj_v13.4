"""Canonical HR use cases."""

from .approve_attendance_adjustment_use_case import ApproveAttendanceAdjustmentUseCase
from .pay_payroll_run_use_case import PayPayrollRunUseCase
from .generate_payroll_run_use_case import GeneratePayrollRunUseCase
from .cancel_payroll_run_use_case import CancelPayrollRunUseCase
from .authorize_payroll_run_use_case import AuthorizePayrollRunUseCase
from .request_leave_use_case import RequestLeaveUseCase
from .reject_leave_use_case import RejectLeaveUseCase
from .cancel_leave_use_case import CancelLeaveUseCase
from .approve_leave_use_case import ApproveLeaveUseCase
from .assign_shift_use_case import AssignShiftUseCase
from .create_contract_type_use_case import CreateContractTypeUseCase
from .create_department_use_case import CreateDepartmentUseCase
from .create_employee_use_case import CreateEmployeeUseCase
from .create_payment_frequency_use_case import CreatePaymentFrequencyUseCase
from .create_position_use_case import CreatePositionUseCase
from .create_rest_day_use_case import CreateRestDayUseCase
from .create_shift_template_use_case import CreateShiftTemplateUseCase
from .create_shift_use_case import CreateShiftUseCase
from .deactivate_employee_use_case import DeactivateEmployeeUseCase
from .recalculate_workday_use_case import RecalculateWorkdayUseCase
from .register_attendance_punch_use_case import RegisterAttendancePunchUseCase
from .register_manual_attendance_use_case import RegisterManualAttendanceUseCase
from .request_attendance_adjustment_use_case import RequestAttendanceAdjustmentUseCase
from .update_employee_use_case import UpdateEmployeeUseCase

__all__ = [
    "PayPayrollRunUseCase",
    "GeneratePayrollRunUseCase",
    "CancelPayrollRunUseCase",
    "AuthorizePayrollRunUseCase",
    "RequestLeaveUseCase",
    "RejectLeaveUseCase",
    "CancelLeaveUseCase",
    "ApproveLeaveUseCase",
    "ApproveAttendanceAdjustmentUseCase",
    "AssignShiftUseCase",
    "CreateContractTypeUseCase",
    "CreateDepartmentUseCase",
    "CreateEmployeeUseCase",
    "CreatePaymentFrequencyUseCase",
    "CreatePositionUseCase",
    "CreateRestDayUseCase",
    "CreateShiftTemplateUseCase",
    "CreateShiftUseCase",
    "DeactivateEmployeeUseCase",
    "RecalculateWorkdayUseCase",
    "RegisterAttendancePunchUseCase",
    "RegisterManualAttendanceUseCase",
    "RequestAttendanceAdjustmentUseCase",
    "UpdateEmployeeUseCase",
]
