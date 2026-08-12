"""Canonical enums for the Customer Service (atención al cliente) bounded
context (CRM-7, master prompt §30-32)."""

from __future__ import annotations

from enum import Enum


class ServiceCaseType(str, Enum):
    QUESTION = "QUESTION"
    REQUEST = "REQUEST"
    COMPLAINT = "COMPLAINT"
    INCIDENT = "INCIDENT"
    RETURN_REQUEST = "RETURN_REQUEST"
    DELIVERY_ISSUE = "DELIVERY_ISSUE"
    PAYMENT_ISSUE = "PAYMENT_ISSUE"
    PRODUCT_QUALITY = "PRODUCT_QUALITY"
    CREDIT_ISSUE = "CREDIT_ISSUE"
    OTHER = "OTHER"


class ServiceCaseStatus(str, Enum):
    NEW = "NEW"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_CUSTOMER = "WAITING_CUSTOMER"
    WAITING_INTERNAL = "WAITING_INTERNAL"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class ServiceCasePriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"
    CRITICAL = "CRITICAL"


class ServiceCaseChannel(str, Enum):
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    WHATSAPP = "WHATSAPP"
    WALK_IN = "WALK_IN"
    WEB = "WEB"
    OTHER = "OTHER"


class EscalationReason(str, Enum):
    """§30-32's escalation criteria list, as a closed vocabulary — the
    agent picks one when escalating (recorded verbatim), this is not a
    policy that decides automatically (unlike LeadQualificationPolicy):
    "Registra motivo/nivel/usuario/fecha/destinatario" describes recording
    fields, not computing a decision from inputs."""

    SLA_BREACHED = "SLA_BREACHED"
    PRIORITY_CUSTOMER = "PRIORITY_CUSTOMER"
    CRITICAL_CASE = "CRITICAL_CASE"
    MULTIPLE_REOPENS = "MULTIPLE_REOPENS"
    FINANCIAL_IMPACT = "FINANCIAL_IMPACT"
    REPUTATIONAL_RISK = "REPUTATIONAL_RISK"
    OTHER = "OTHER"


class SLABreachStatus(str, Enum):
    """ON_TIME/AT_RISK/BREACHED are never persisted — same reasoning as
    CRMWorkItemStatus.OVERDUE (CRM-6): nothing "transitions" an SLA into
    BREACHED, it just becomes true once ``now`` passes
    ``resolution_due_at`` while the instance is still open. Only PAUSED and
    COMPLETED are explicit, event-driven states stored on ``SLAInstance``;
    ``effective_breach_status()`` computes the other three dynamically. See
    SLAInstance's docstring."""

    ON_TIME = "ON_TIME"
    AT_RISK = "AT_RISK"
    BREACHED = "BREACHED"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
