"""Domain models for the RRHH bounded context."""

from .entities import (
    AttendanceRecord,
    Employee,
    LeaveRequest,
    PayrollPayment,
    PayrollRecord,
    ShiftAssignment,
    ShiftRole,
)
from .policies import (
    AttendanceHoursPolicy,
    AttendanceJustificationPolicy,
    EmployeeEligibilityPolicy,
    PayrollPeriodPolicy,
    RestDayPolicy,
    VacationOverlapPolicy,
)
from .strategies import (
    FixedAmountStrategy,
    HourlyPayStrategy,
    PayrollConceptCalculator,
    PercentageStrategy,
)

__all__ = [
    "AttendanceRecord",
    "Employee",
    "LeaveRequest",
    "PayrollPayment",
    "PayrollRecord",
    "ShiftAssignment",
    "ShiftRole",
    "AttendanceHoursPolicy",
    "AttendanceJustificationPolicy",
    "EmployeeEligibilityPolicy",
    "PayrollPeriodPolicy",
    "RestDayPolicy",
    "VacationOverlapPolicy",
    "FixedAmountStrategy",
    "HourlyPayStrategy",
    "PayrollConceptCalculator",
    "PercentageStrategy",
]
