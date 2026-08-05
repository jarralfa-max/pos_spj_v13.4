"""Closed Cash Register domain catalogs."""
from enum import Enum


class DeviceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BLOCKED = "BLOCKED"


class CashShiftStatus(str, Enum):
    OPEN = "OPEN"
    SUSPENDED = "SUSPENDED"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class CashMovementDirection(str, Enum):
    INFLOW = "INFLOW"
    OUTFLOW = "OUTFLOW"


class CashMovementType(str, Enum):
    OPENING_FLOAT = "OPENING_FLOAT"
    CASH_SALE = "CASH_SALE"
    CASH_REFUND = "CASH_REFUND"
    MANUAL_INCOME = "MANUAL_INCOME"
    MANUAL_WITHDRAWAL = "MANUAL_WITHDRAWAL"
    SAFE_DROP = "SAFE_DROP"
    HANDOVER = "HANDOVER"
    REVERSAL = "REVERSAL"
    ADJUSTMENT = "ADJUSTMENT"


class BlindCountStatus(str, Enum):
    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class CashDifferenceStatus(str, Enum):
    DETECTED = "DETECTED"
    EXPLAINED = "EXPLAINED"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"


class CashDifferenceClassification(str, Enum):
    SHORTAGE = "SHORTAGE"
    OVERAGE = "OVERAGE"


class CashDifferenceSeverity(str, Enum):
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"
    REVIEW = "REVIEW"
    CRITICAL = "CRITICAL"


class CashHandoverStatus(str, Enum):
    PREPARED = "PREPARED"
    DELIVERED = "DELIVERED"
    RECEIVED = "RECEIVED"
    DISPUTED = "DISPUTED"
