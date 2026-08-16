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


class CRMAutomationTrigger(str, Enum):
    """§56: automation triggers. Split into two real families, not one
    uniform list — half are genuine domain events this bounded context (or
    a sibling: customer_service, customers) already publishes today
    (EVENT_TRIGGERS, reactive — fire the moment the event happens); the
    other half are DERIVED/computed conditions (idle N days, overdue,
    SLA at-risk/breached) that no entity ever transitions "into" as a
    discrete state change — same reasoning CRMWorkItemStatus.OVERDUE and
    SLAInstance's breach_status already document. Nothing in this repo
    polls/schedules today (confirmed: no cron/background-job mechanism
    exists anywhere), so TIME_BASED_TRIGGERS are evaluated by an explicit,
    callable sweep (EvaluateTimeBasedAutomationTriggersUseCase) rather than
    a fabricated always-on scheduler — see that use case's own docstring."""

    LEAD_CREATED = "LEAD_CREATED"
    LEAD_IDLE = "LEAD_IDLE"
    OPPORTUNITY_STAGE_CHANGED = "OPPORTUNITY_STAGE_CHANGED"
    OPPORTUNITY_IDLE = "OPPORTUNITY_IDLE"
    OPPORTUNITY_OVERDUE = "OPPORTUNITY_OVERDUE"
    CUSTOMER_INACTIVE = "CUSTOMER_INACTIVE"
    CASE_CREATED = "CASE_CREATED"
    SLA_AT_RISK = "SLA_AT_RISK"
    SLA_BREACHED = "SLA_BREACHED"
    CREDIT_REVIEW_DUE = "CREDIT_REVIEW_DUE"


EVENT_TRIGGERS = frozenset({
    CRMAutomationTrigger.LEAD_CREATED,
    CRMAutomationTrigger.OPPORTUNITY_STAGE_CHANGED,
    CRMAutomationTrigger.CASE_CREATED,
})

TIME_BASED_TRIGGERS = frozenset({
    CRMAutomationTrigger.LEAD_IDLE,
    CRMAutomationTrigger.OPPORTUNITY_IDLE,
    CRMAutomationTrigger.OPPORTUNITY_OVERDUE,
    CRMAutomationTrigger.CUSTOMER_INACTIVE,
    CRMAutomationTrigger.SLA_AT_RISK,
    CRMAutomationTrigger.SLA_BREACHED,
    CRMAutomationTrigger.CREDIT_REVIEW_DUE,
})


class CRMAutomationAction(str, Enum):
    """§56's exact action list. Each is executed by calling an EXISTING,
    already-authorized use case (CreateCRMTaskUseCase, AssignLeadUseCase/
    AssignOpportunityUseCase/AssignCustomerOwnerUseCase depending on the
    target entity, EscalateServiceCaseUseCase, tag/segment-membership use
    cases) — never a raw table write and never arbitrary code, satisfying
    "No permitir scripts arbitrarios. Usar reglas declarativas." literally:
    action_config on CRMAutomationRule is a flat JSON parameter dict, not
    a script body."""

    CREATE_TASK = "CREATE_TASK"
    ASSIGN_OWNER = "ASSIGN_OWNER"
    SEND_NOTIFICATION = "SEND_NOTIFICATION"
    CHANGE_PRIORITY = "CHANGE_PRIORITY"
    ESCALATE_CASE = "ESCALATE_CASE"
    ADD_TAG = "ADD_TAG"
    ADD_TO_SEGMENT = "ADD_TO_SEGMENT"


class CRMAutomationExecutionStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class CRMSyncConflictType(str, Enum):
    """§92: the 4 conflict types that belong to ``CRMSyncConflict`` — the
    other 6 (customer/contact/address/consent/credit/duplicate) are
    ``CustomerSyncConflictType`` in backend/domain/customers/enums.py.
    CASE_ASSIGNMENT_CONFLICT lives here (not in customer_service's own
    enums) because §92 groups it under CRMSyncConflict explicitly, mirroring
    how CRM-6/CRM-26 already treat Service Cases as part of the wider CRM
    relationship surface for cross-cutting concerns."""

    LEAD_ASSIGNMENT_CONFLICT = "LEAD_ASSIGNMENT_CONFLICT"
    OPPORTUNITY_STAGE_CONFLICT = "OPPORTUNITY_STAGE_CONFLICT"
    TASK_STATUS_CONFLICT = "TASK_STATUS_CONFLICT"
    CASE_ASSIGNMENT_CONFLICT = "CASE_ASSIGNMENT_CONFLICT"


class SyncConflictStatus(str, Enum):
    """Mirrors backend/domain/customers/enums.py's SyncConflictStatus —
    duplicated, not imported, same boundary discipline this package already
    keeps for exceptions/events (never cross-import domain vocabulary
    between customers and crm)."""

    OPEN = "OPEN"
    RESOLVED_LOCAL = "RESOLVED_LOCAL"
    RESOLVED_REMOTE = "RESOLVED_REMOTE"
    RESOLVED_MERGED = "RESOLVED_MERGED"


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
