"""Canonical enums for the Customer Master bounded context (CRM-3, master
prompt §12-15)."""

from __future__ import annotations

from enum import Enum


class CustomerType(str, Enum):
    INDIVIDUAL = "INDIVIDUAL"
    BUSINESS = "BUSINESS"
    PUBLIC_CUSTOMER = "PUBLIC_CUSTOMER"
    EMPLOYEE = "EMPLOYEE"
    INTERNAL = "INTERNAL"
    OTHER = "OTHER"


class CustomerStatus(str, Enum):
    DRAFT = "DRAFT"
    PROSPECT = "PROSPECT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    BLOCKED = "BLOCKED"
    CLOSED = "CLOSED"
    MERGED = "MERGED"
    ANONYMIZED = "ANONYMIZED"


class LifecycleStage(str, Enum):
    PROSPECT = "PROSPECT"
    LEAD = "LEAD"
    QUALIFIED = "QUALIFIED"
    CUSTOMER = "CUSTOMER"
    REPEAT_CUSTOMER = "REPEAT_CUSTOMER"
    AT_RISK = "AT_RISK"
    INACTIVE = "INACTIVE"
    LOST = "LOST"


class ContactDecisionRole(str, Enum):
    DECISION_MAKER = "DECISION_MAKER"
    INFLUENCER = "INFLUENCER"
    BUYER = "BUYER"
    USER = "USER"
    FINANCE_CONTACT = "FINANCE_CONTACT"
    DELIVERY_CONTACT = "DELIVERY_CONTACT"
    OTHER = "OTHER"


class AddressType(str, Enum):
    FISCAL = "FISCAL"
    BILLING = "BILLING"
    DELIVERY = "DELIVERY"
    COMMERCIAL = "COMMERCIAL"
    PERSONAL = "PERSONAL"


class ValidationStatus(str, Enum):
    """Shared by addresses and tax profiles (§14-15)."""

    MANUAL = "MANUAL"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"
