"""Canonical enums for the Customer Privacy bounded context (CRM-9, master
prompt §41-44)."""

from __future__ import annotations

from enum import Enum


class ConsentType(str, Enum):
    PRIVACY_NOTICE = "PRIVACY_NOTICE"
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    SMS = "SMS"
    MARKETING = "MARKETING"
    PROFILING = "PROFILING"
    TERMS = "TERMS"
    DATA_SHARING = "DATA_SHARING"


class ConsentStatus(str, Enum):
    """EXPIRED is never persisted — nothing "transitions" a consent into
    EXPIRED, it just becomes true once ``now`` passes ``expires_at`` while
    the consent is still GRANTED, same reasoning as
    CRMWorkItemStatus.OVERDUE (CRM-6) / SLABreachStatus (CRM-7). The stored
    ``status`` column only ever holds PENDING/GRANTED/WITHDRAWN/
    NOT_REQUIRED; ``CustomerConsent.effective_status()`` computes EXPIRED
    dynamically."""

    PENDING = "PENDING"
    GRANTED = "GRANTED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"
    NOT_REQUIRED = "NOT_REQUIRED"


class ConsentChannel(str, Enum):
    """Where/how the consent was captured — evidence of the capture
    context, not a communication channel preference (see
    CustomerCommunicationPreference for that)."""

    WEB = "WEB"
    WHATSAPP = "WHATSAPP"
    IN_PERSON = "IN_PERSON"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    IMPORTED = "IMPORTED"
    OTHER = "OTHER"


class PreferredChannel(str, Enum):
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    SMS = "SMS"
    PHONE = "PHONE"
    NONE = "NONE"


class PrivacyRequestType(str, Enum):
    ACCESS = "ACCESS"
    RECTIFICATION = "RECTIFICATION"
    CANCELLATION = "CANCELLATION"
    OPPOSITION = "OPPOSITION"
    EXPORT = "EXPORT"
    ANONYMIZATION = "ANONYMIZATION"
    CONSENT_WITHDRAWAL = "CONSENT_WITHDRAWAL"


class PrivacyRequestStatus(str, Enum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
