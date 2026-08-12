"""Canonical enums for the Customer Credit bounded context (CRM-8, master
prompt §37-40)."""

from __future__ import annotations

from enum import Enum


class CreditProfileStatus(str, Enum):
    """§37-40's literal state list has no REJECTED — a rejected request
    lands in CLOSED with ``close_reason`` recording why (see
    CustomerCreditProfile.reject()). NOT_CONFIGURED is never stored on a
    row — it is what a query service reports when no profile exists yet
    for a customer (the repository returns no row, not a row with this
    status); see CustomerCreditProfile's module docstring."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    UNDER_REVIEW = "UNDER_REVIEW"
    AUTHORIZED = "AUTHORIZED"
    SUSPENDED = "SUSPENDED"
    BLOCKED = "BLOCKED"
    CLOSED = "CLOSED"


class CreditRiskLevel(str, Enum):
    """Not enumerated explicitly in §37-40 (only "risk_level" is named as a
    field) — a conventional four-tier scale, same shape this repo already
    uses elsewhere for risk/severity axes."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"
