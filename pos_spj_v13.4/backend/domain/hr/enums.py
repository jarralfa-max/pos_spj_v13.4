"""Canonical enumerations for the HR bounded context."""

from __future__ import annotations

from enum import Enum


class EmploymentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ON_LEAVE = "ON_LEAVE"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"


class ContractType(str, Enum):
    PERMANENT = "PERMANENT"
    FIXED_TERM = "FIXED_TERM"
    TEMPORARY = "TEMPORARY"
    INTERNSHIP = "INTERNSHIP"
    HOURLY = "HOURLY"


class PaymentFrequency(str, Enum):
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"      # catorcenal
    SEMIMONTHLY = "SEMIMONTHLY"  # quincenal
    MONTHLY = "MONTHLY"


class PunchType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class AttendanceSource(str, Enum):
    CASH_REGISTER = "CASH_REGISTER"
    MANUAL = "MANUAL"
    TIME_CLOCK = "TIME_CLOCK"
    MOBILE = "MOBILE"
    SYSTEM = "SYSTEM"
    # Reserved for future biometric/token devices:
    FINGERPRINT = "FINGERPRINT"
    FACE_RECOGNITION = "FACE_RECOGNITION"
    QR = "QR"
    RFID = "RFID"


class WorkdayStatus(str, Enum):
    OPEN = "OPEN"                # entry registered, no exit yet
    COMPLETE = "COMPLETE"        # entry + exit
    INCIDENT = "INCIDENT"        # missing entry/exit or anomaly
    ADJUSTED = "ADJUSTED"        # corrected via an approved adjustment


class AttendanceIncidentType(str, Enum):
    MISSING_ENTRY = "MISSING_ENTRY"
    MISSING_EXIT = "MISSING_EXIT"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"
    OUT_OF_SEQUENCE = "OUT_OF_SEQUENCE"


class AdjustmentStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class LeaveType(str, Enum):
    VACATION = "VACATION"
    PAID_LEAVE = "PAID_LEAVE"
    UNPAID_LEAVE = "UNPAID_LEAVE"
    SICK_LEAVE = "SICK_LEAVE"
    ABSENCE_JUSTIFICATION = "ABSENCE_JUSTIFICATION"


class LeaveStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PayrollRunStatus(str, Enum):
    DRAFT = "DRAFT"
    CALCULATED = "CALCULATED"
    UNDER_REVIEW = "UNDER_REVIEW"
    AUTHORIZED = "AUTHORIZED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class PayrollConcept(str, Enum):
    BASE_SALARY = "BASE_SALARY"
    OVERTIME = "OVERTIME"
    BONUS = "BONUS"
    COMMISSION = "COMMISSION"
    VACATION = "VACATION"
    PAID_LEAVE = "PAID_LEAVE"
    ABSENCE_DEDUCTION = "ABSENCE_DEDUCTION"
    LATE_DEDUCTION = "LATE_DEDUCTION"
    LOAN_DEDUCTION = "LOAN_DEDUCTION"
    ADVANCE_DEDUCTION = "ADVANCE_DEDUCTION"
    ADJUSTMENT = "ADJUSTMENT"


#: Concepts that subtract from gross pay.
DEDUCTION_CONCEPTS = frozenset({
    PayrollConcept.ABSENCE_DEDUCTION,
    PayrollConcept.LATE_DEDUCTION,
    PayrollConcept.LOAN_DEDUCTION,
    PayrollConcept.ADVANCE_DEDUCTION,
})


class PaymentMethod(str, Enum):
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    CHECK = "CHECK"


class Weekday(int, Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6
