"""Closed catalogs for the Payments bounded context.

Provider transport details (Mercado Pago Checkout, QR, Point) deliberately
live outside the domain. These values describe our local payment lifecycle.
"""
from enum import Enum


class PaymentChannel(str, Enum):
    POS = "POS"
    WHATSAPP = "WHATSAPP"


class PaymentMethod(str, Enum):
    CHECKOUT = "CHECKOUT"
    QR = "QR"
    POINT = "POINT"


class PaymentPurpose(str, Enum):
    FULL = "FULL"
    DEPOSIT = "DEPOSIT"
    BALANCE = "BALANCE"


class PaymentIntentStatus(str, Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REFUNDED = "REFUNDED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
