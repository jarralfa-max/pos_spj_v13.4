"""Canonical enums for the Commercial Instruments bounded context (LOY-12,
master prompt §21-22, §7.2). Separate package from ``backend.domain.loyalty``
— coupons/vouchers are commercial instruments in their own right (e.g.
``SUPPLIER_FUNDED``/``EMPLOYEE_GRANTED`` are not loyalty concepts at all),
not a sub-type of the points ledger."""

from __future__ import annotations

from enum import Enum


class CouponType(str, Enum):
    """§21."""
    PUBLIC_CODE = "PUBLIC_CODE"
    UNIQUE_CODE = "UNIQUE_CODE"
    AUTOMATIC = "AUTOMATIC"
    PERSONALIZED = "PERSONALIZED"
    BIRTHDAY = "BIRTHDAY"
    REFERRAL = "REFERRAL"
    WIN_BACK = "WIN_BACK"
    LOYALTY_REWARD = "LOYALTY_REWARD"
    SUPPLIER_FUNDED = "SUPPLIER_FUNDED"
    EMPLOYEE_GRANTED = "EMPLOYEE_GRANTED"


class CommercialBenefitType(str, Enum):
    """§21 'Beneficios' — shared by coupons and (later) vouchers."""
    FIXED_AMOUNT = "FIXED_AMOUNT"
    PERCENTAGE = "PERCENTAGE"
    FREE_PRODUCT = "FREE_PRODUCT"
    BUY_X_GET_Y = "BUY_X_GET_Y"
    FREE_DELIVERY = "FREE_DELIVERY"
    PRICE_OVERRIDE = "PRICE_OVERRIDE"


class CouponInstanceStatus(str, Enum):
    """§21 'Estados de instancia'."""
    ISSUED = "ISSUED"
    ACTIVE = "ACTIVE"
    RESERVED = "RESERVED"
    REDEEMED = "REDEEMED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class VoucherType(str, Enum):
    """§22."""
    REFUND_VOUCHER = "REFUND_VOUCHER"
    STORE_CREDIT = "STORE_CREDIT"
    PROMOTIONAL_VOUCHER = "PROMOTIONAL_VOUCHER"
    COMPENSATION_VOUCHER = "COMPENSATION_VOUCHER"
    PREPAID_VOUCHER = "PREPAID_VOUCHER"
    SUPPLIER_FUNDED_VOUCHER = "SUPPLIER_FUNDED_VOUCHER"
    EMPLOYEE_AUTHORIZED_VOUCHER = "EMPLOYEE_AUTHORIZED_VOUCHER"


class VoucherInstanceStatus(str, Enum):
    """§22."""
    ISSUED = "ISSUED"
    ACTIVE = "ACTIVE"
    PARTIALLY_REDEEMED = "PARTIALLY_REDEEMED"
    RESERVED = "RESERVED"
    REDEEMED = "REDEEMED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    REVERSED = "REVERSED"


class VoucherTransactionType(str, Enum):
    """§22 'Ledger'."""
    ISSUE = "ISSUE"
    REDEEM = "REDEEM"
    RESERVE = "RESERVE"
    RELEASE = "RELEASE"
    RELOAD = "RELOAD"
    EXPIRE = "EXPIRE"
    ADJUSTMENT = "ADJUSTMENT"
    REFUND = "REFUND"
    REVERSAL = "REVERSAL"


class VoucherTransactionStatus(str, Enum):
    """Same vocabulary/semantics as `backend.domain.loyalty.enums.
    TransactionStatus` — a ledger entry's status governs business rules
    (can this reservation still be released?), never the balance sum
    itself (see `VoucherBalancePolicy`'s own docstring)."""
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    REVERSED = "REVERSED"
    CANCELLED = "CANCELLED"
