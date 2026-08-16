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


class CustomerSyncConflictType(str, Enum):
    """§92: the 6 conflict types that belong to the Customer Master half of
    ``CustomerSyncConflict`` (the other 4 — lead/opportunity/task/case — are
    ``CRMSyncConflictType`` in backend/domain/crm/enums.py, since §92 names
    exactly TWO conflict entities total, not one per sub-package)."""

    CUSTOMER_UPDATED_REMOTELY = "CUSTOMER_UPDATED_REMOTELY"
    DUPLICATE_CREATED = "DUPLICATE_CREATED"
    CONTACT_CONFLICT = "CONTACT_CONFLICT"
    ADDRESS_CONFLICT = "ADDRESS_CONFLICT"
    CONSENT_CONFLICT = "CONSENT_CONFLICT"
    CREDIT_CONFLICT = "CREDIT_CONFLICT"


class SyncConflictStatus(str, Enum):
    """Shared resolution lifecycle for CustomerSyncConflict/CRMSyncConflict.
    §92: "no sobrescribir silenciosamente" — a conflict stays OPEN, blocking
    the incoming write, until a human explicitly picks one of the three
    RESOLVED_* outcomes."""

    OPEN = "OPEN"
    RESOLVED_LOCAL = "RESOLVED_LOCAL"
    RESOLVED_REMOTE = "RESOLVED_REMOTE"
    RESOLVED_MERGED = "RESOLVED_MERGED"


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


class DuplicateCandidateStatus(str, Enum):
    """§45's literal state list for CustomerDuplicateCandidate."""

    DETECTED = "DETECTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    CONFIRMED_DUPLICATE = "CONFIRMED_DUPLICATE"
    DISMISSED = "DISMISSED"
    MERGED = "MERGED"


class CustomerMergeStatus(str, Enum):
    """CustomerMergeRecord lifecycle. §45 describes the merge *flow*
    ("selecciona maestro, preserva referencias... audita") but names no
    explicit state list the way it does for duplicates — this collapses
    "approved" and "executed" into one hot-authorized step (see
    ExecuteCustomerMergeUseCase) rather than inventing a separate persisted
    APPROVED-but-not-yet-executed state nothing in the master prompt asks
    for and that would have no use case of its own."""

    PROPOSED = "PROPOSED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


class DataQualityIssueStatus(str, Enum):
    """§46's literal state list for CustomerDataQualityIssue."""

    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CORRECTED = "CORRECTED"
    DISMISSED = "DISMISSED"


class DataQualityRuleCode(str, Enum):
    """The subset of §46's rule list this phase evaluates directly — pure
    ``customers``-package data only (no reach into other bounded
    contexts). See CustomerDataQualityService's docstring for the other
    five §46 rules (consentimiento faltante, crédito inconsistente, lead
    sin seguimiento, oportunidad sin próxima actividad, caso sin
    propietario), deferred to CRM-12 (Customer 360). "Duplicado probable"
    is deliberately NOT a rule here either — that surface is
    CustomerDuplicateCandidate's own dedicated workflow, not re-flagged as
    a second, overlapping mechanism."""

    INCOMPLETE_NAME = "INCOMPLETE_NAME"
    INVALID_PHONE = "INVALID_PHONE"
    INVALID_EMAIL = "INVALID_EMAIL"
    INVALID_TAX_ID = "INVALID_TAX_ID"
    INCOMPLETE_ADDRESS = "INCOMPLETE_ADDRESS"


class ImportBatchStatus(str, Enum):
    """CustomerImportBatch lifecycle (§47). PENDING_APPROVAL only occurs for
    ``is_sensitive=True`` batches (§73: "quien importa no aprueba una
    importación sensible" — a second, distinct approver is required before
    rows are written); non-sensitive batches go straight to PROCESSING."""

    PENDING_APPROVAL = "PENDING_APPROVAL"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
