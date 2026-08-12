"""Domain exceptions for the CRM (relationship) bounded context (CRM-2, §59-76).

Covers Leads, Opportunities/Pipeline, Activities, Service Cases. Mirrors
backend/domain/customers/exceptions.py's shape so both halves of the
Clientes/CRM module share one security vocabulary.
"""

from __future__ import annotations


class CRMDomainError(Exception):
    """Base for CRM (leads/opportunities/activities/cases) rule violations."""


class CRMPermissionDeniedError(CRMDomainError):
    """The user lacks the granular permission the action requires."""


class CRMConfigurationError(CRMDomainError):
    """A security-sensitive component was built without its mandatory wiring.
    Fail closed: never allow an operation to proceed on an unconfigured
    authorization gate."""


class CRMScopeError(CRMDomainError):
    """The user's granted data scope does not cover the requested lead/
    opportunity/case (owner, team, branch, territory or portfolio mismatch)."""


class CRMSegregationOfDutiesError(CRMDomainError):
    """The same user cannot hold two conflicting roles in one operation."""


# ── CRM-4: Leads (§16-18, §93) ───────────────────────────────────────────────

class LeadNotFoundError(CRMDomainError):
    """Referenced a lead_id that does not exist."""


class InvalidLeadStateError(CRMDomainError):
    """A lifecycle transition is not valid from the lead's current status."""


class LeadAlreadyConvertedError(CRMDomainError):
    """An operation was attempted on a lead already CONVERTED (terminal)."""


class LeadQualificationFailedError(CRMDomainError):
    """A qualification attempt was built with missing/invalid criteria for
    the selected QualificationModel."""


class InvalidLeadCodeError(CRMDomainError):
    """A LeadCode (folio) does not match the canonical LEAD-NNNNNN shape."""


# ── CRM-5: Opportunities / pipeline (§19-22, §93) ────────────────────────────

class OpportunityNotFoundError(CRMDomainError):
    """Referenced an opportunity_id that does not exist."""


class InvalidOpportunityStateError(CRMDomainError):
    """A lifecycle transition (assign/hold/resume/win/lose/cancel/reopen) is
    not valid from the opportunity's current status. Named to match this
    module's existing ``Invalid<Entity>StateError`` convention
    (``InvalidLeadStateError``, ``InvalidCustomerStateError``) rather than
    the master prompt's literal ``OpportunityStateInvalidError`` — kept
    consistent with the CRM-3/CRM-4 precedent, not a fresh naming choice."""


class OpportunityStageTransitionNotAllowedError(CRMDomainError):
    """A stage move violates CRMStageTransitionPolicy: wrong opportunity
    status, inactive target stage, missing required fields, insufficient
    logged activity, or a backward move without a reason. Distinct from
    InvalidOpportunityStateError because a stage move can be rejected even
    when the opportunity's overall status transition would otherwise be
    legal."""


class InvalidOpportunityCodeError(CRMDomainError):
    """An OpportunityCode (folio) does not match the canonical OPP-NNNNNN
    shape."""


class InvalidStageDefinitionError(CRMDomainError):
    """A CRMStageDefinition was built with invalid configuration (e.g. a
    stage flagged both won and lost, or an out-of-range default
    probability)."""


# ── CRM-6: Activities / Tasks / Notes / Reminders (§23-26, §93) ─────────────

class CRMActivityNotFoundError(CRMDomainError):
    """Referenced an activity_id that does not exist. Name matches §93
    literally (unlike InvalidOpportunityStateError et al., this one already
    matched the established Invalid*/​*NotFoundError conventions)."""


class InvalidCRMActivityStateError(CRMDomainError):
    """A lifecycle transition (start/complete/cancel/reschedule) is not
    valid from the activity's current status."""


class CRMTaskNotFoundError(CRMDomainError):
    """Referenced a task_id that does not exist."""


class InvalidCRMTaskStateError(CRMDomainError):
    """A lifecycle transition (assign/complete/cancel/reschedule) is not
    valid from the task's current status."""


class CRMNoteNotFoundError(CRMDomainError):
    """Referenced a note_id that does not exist."""


class InvalidCRMNoteError(CRMDomainError):
    """A CRMNote was built with invalid content (e.g. empty body)."""


class InvalidCRMReminderError(CRMDomainError):
    """A CRMReminder was built without a valid channel/recipient/schedule,
    or without a task/activity to attach to."""
