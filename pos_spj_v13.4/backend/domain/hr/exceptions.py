"""Specific HR domain and application exceptions."""

from __future__ import annotations


class HRDomainError(Exception):
    """Base class for known HR errors."""


class EmployeeNotFoundError(HRDomainError):
    pass


class EmployeeInactiveError(HRDomainError):
    pass


class UserEmployeeLinkRequiredError(HRDomainError):
    pass


class AttendanceAlreadyOpenError(HRDomainError):
    pass


class AttendanceMissingEntryError(HRDomainError):
    pass


class AttendanceInvalidSequenceError(HRDomainError):
    pass


class AttendanceAdjustmentNotAuthorizedError(HRDomainError):
    pass


class LeaveOverlapError(HRDomainError):
    pass


class InsufficientLeaveBalanceError(HRDomainError):
    pass


class PayrollAlreadyPaidError(HRDomainError):
    pass


class PayrollNotAuthorizedError(HRDomainError):
    pass


class PayrollInvalidStateError(HRDomainError):
    pass


class PermissionDeniedError(HRDomainError):
    pass
