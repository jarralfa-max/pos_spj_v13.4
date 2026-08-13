"""Canonical enums for the CRM (relationship) bounded context (CRM-4,
master prompt §16-18)."""

from __future__ import annotations

from enum import Enum


class LeadStatus(str, Enum):
    NEW = "NEW"
    ASSIGNED = "ASSIGNED"
    CONTACTED = "CONTACTED"
    NURTURING = "NURTURING"
    QUALIFIED = "QUALIFIED"
    UNQUALIFIED = "UNQUALIFIED"
    CONVERTED = "CONVERTED"
    LOST = "LOST"
    ARCHIVED = "ARCHIVED"


class LeadSource(str, Enum):
    WALK_IN = "WALK_IN"
    POS = "POS"
    WHATSAPP = "WHATSAPP"
    PHONE = "PHONE"
    REFERRAL = "REFERRAL"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    WEBSITE = "WEBSITE"
    CAMPAIGN = "CAMPAIGN"
    IMPORT = "IMPORT"
    SALES_REP = "SALES_REP"
    OTHER = "OTHER"


class LeadPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class QualificationModel(str, Enum):
    """§17: "No hardcodear una metodología única" — a lead may be qualified
    under any of these; the model used is recorded on the evidence entity."""

    MANUAL = "MANUAL"
    SCORE_BASED = "SCORE_BASED"
    BANT_LIKE = "BANT_LIKE"
    CUSTOM_RULE = "CUSTOM_RULE"


class QualificationDecision(str, Enum):
    QUALIFIED = "QUALIFIED"
    UNQUALIFIED = "UNQUALIFIED"


class OpportunityStatus(str, Enum):
    """§19-22: OPEN/ON_HOLD are the only statuses a stage change is allowed
    from — WON/LOST/CANCELLED are terminal. The pipeline *stage* within OPEN
    is a separate, configurable concept — see CRMStageDefinition, never a
    hardcoded enum branch."""

    OPEN = "OPEN"
    WON = "WON"
    LOST = "LOST"
    CANCELLED = "CANCELLED"
    ON_HOLD = "ON_HOLD"


class CRMRelatedEntityType(str, Enum):
    """What an Activity/Task/Note/Reminder is *about*. A single polymorphic
    (type, id) pair instead of four nullable FK columns per entity — same
    trade-off this repo already accepts elsewhere for cross-context opaque
    references (e.g. Opportunity.source_lead_id). CASE is reserved for
    CRM-7 (Service Cases don't exist yet) — no use case in CRM-6 produces
    it, but the value exists now so CRM-7 doesn't have to widen a CHECK
    constraint later."""

    LEAD = "LEAD"
    OPPORTUNITY = "OPPORTUNITY"
    CUSTOMER = "CUSTOMER"
    CASE = "CASE"


class CRMActivityType(str, Enum):
    """§23-26's "Tipos" list minus TASK/NOTE — those two are modeled as
    their own entities (CRMTask, CRMNote) with their own lifecycle/
    permissions, not as CRMActivity type values; folding them in here would
    blur exactly the entity boundary the rest of this bounded context keeps
    sharp (mirrors CRM-2's permission-format decision and CRM-3's Invalid*
    naming decision — master-prompt literalism adjusted for consistency)."""

    CALL = "CALL"
    MEETING = "MEETING"
    VISIT = "VISIT"
    EMAIL = "EMAIL"
    WHATSAPP = "WHATSAPP"
    FOLLOW_UP = "FOLLOW_UP"
    QUOTE_REVIEW = "QUOTE_REVIEW"
    PAYMENT_FOLLOW_UP = "PAYMENT_FOLLOW_UP"
    OTHER = "OTHER"


class CRMWorkItemStatus(str, Enum):
    """Shared status vocabulary for CRMActivity and CRMTask (§23-26).
    OVERDUE is intentionally never persisted — nothing "transitions" an
    item into OVERDUE, it just becomes true once ``now > scheduled_at/
    due_at`` and the item is still open, so storing it would need a
    background job to keep rows truthful. The stored ``status`` column only
    ever holds PLANNED/IN_PROGRESS/COMPLETED/CANCELLED; ``effective_status()``
    on each entity computes OVERDUE dynamically. OVERDUE is still a member
    of this enum so the query/display layer has one canonical value to
    report (§23-26: "Vencida se muestra con estado+icono, no solo color")."""

    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    OVERDUE = "OVERDUE"


class ReminderChannel(str, Enum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    WHATSAPP_INTERNAL = "WHATSAPP_INTERNAL"
    PUSH_FUTURE = "PUSH_FUTURE"


class OwnershipType(str, Enum):
    """§33-36: "con historial de asignación — no solo vendedor_id plano".
    PRIMARY is the only type kept in sync with the fast-path denormalized
    Customer.account_owner_user_id field CRM-3 built for OWN-scope
    resolution (see CustomerDataScopeResolver) — the other types are
    informational roles that don't affect data-scope resolution."""

    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    ACCOUNT_MANAGER = "ACCOUNT_MANAGER"
    CREDIT_MANAGER = "CREDIT_MANAGER"
    SERVICE_OWNER = "SERVICE_OWNER"


class SegmentMembershipSource(str, Enum):
    """§33-36: "MANUAL, RULE_BASED, IMPORTED, ANALYTICS_GENERATED" — how a
    customer ended up in a segment. Lives on CustomerSegmentMembership, not
    on CustomerSegment itself: the same segment can accumulate members from
    more than one source over time (a manually-added member and a
    BI-suggested one can coexist in the same segment), so the source is a
    fact about the membership, not a property of the segment definition."""

    MANUAL = "MANUAL"
    RULE_BASED = "RULE_BASED"
    IMPORTED = "IMPORTED"
    ANALYTICS_GENERATED = "ANALYTICS_GENERATED"
