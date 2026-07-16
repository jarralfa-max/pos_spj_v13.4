"""Domain exceptions for the HR bounded context."""

from __future__ import annotations


class HRDomainError(Exception):
    """Base error for every HR domain violation."""


class EmployeeNotFoundError(HRDomainError):
    pass


class EmployeeInactiveError(HRDomainError):
    pass


class UserEmployeeLinkRequiredError(HRDomainError):
    """Raised when an operation needs a user linked to an active employee."""


class DuplicateEmployeeCodeError(HRDomainError):
    pass


class AttendanceAlreadyOpenError(HRDomainError):
    """An open entry already exists for the employee/workday."""


class AttendanceMissingEntryError(HRDomainError):
    """An exit was requested but no open entry exists."""


class AttendanceInvalidSequenceError(HRDomainError):
    """Punches out of the expected ENTRY→EXIT order."""


class ImmutablePunchError(HRDomainError):
    """A registered punch cannot be modified; use an adjustment."""


class AttendanceAdjustmentNotAuthorizedError(HRDomainError):
    pass


class InvalidAdjustmentStateError(HRDomainError):
    pass


class LeaveOverlapError(HRDomainError):
    pass


class InsufficientLeaveBalanceError(HRDomainError):
    pass


class InvalidLeaveStateError(HRDomainError):
    pass


class InvalidLeaveDatesError(HRDomainError):
    pass


class PayrollAlreadyPaidError(HRDomainError):
    pass


class PayrollNotAuthorizedError(HRDomainError):
    pass


class PayrollInvalidStateError(HRDomainError):
    pass


class PayrollEmptyRunError(HRDomainError):
    pass


class ShiftOverlapError(HRDomainError):
    pass


class InvalidShiftError(HRDomainError):
    pass


class PermissionDeniedError(HRDomainError):
    pass
