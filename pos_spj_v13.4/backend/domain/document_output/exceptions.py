"""Domain exceptions for the Document Output bounded context — SET-11.
Mirrors backend/domain/settings/exceptions.py's shape.
"""

from __future__ import annotations


class DocumentOutputDomainError(Exception):
    """Base for Document Output rule violations."""


class DocumentInvalidValueError(DocumentOutputDomainError):
    """A field does not satisfy its validation rule."""


class DocumentTemplateNotFoundError(DocumentOutputDomainError):
    """Referenced a `DocumentTemplate` id that does not exist."""


class TemplateVersionNotFoundError(DocumentOutputDomainError):
    """Referenced a `DocumentTemplateVersion` id that does not exist."""


class TemplateVersionInactiveError(DocumentOutputDomainError):
    """Requested to print with a `DocumentTemplateVersion` that isn't
    ACTIVE — rendering must always use the currently active version."""


class TemplateTransitionNotAllowedError(DocumentOutputDomainError):
    """The template version is not in a state that allows the requested
    transition."""


class PrintJobNotFoundError(DocumentOutputDomainError):
    """Referenced a `PrintJob` id that does not exist."""


class PrintJobTransitionNotAllowedError(DocumentOutputDomainError):
    """The print job is not in a state that allows the requested
    transition."""


class PrintJobAlreadyCompletedError(DocumentOutputDomainError):
    """Attempted to cancel/retry a job that already reached a terminal
    state (PRINTED/CANCELLED/DEAD_LETTER)."""


class DocumentReprintNotAllowedError(DocumentOutputDomainError):
    """A reprint request is missing what §33 requires: a reason, and a
    reference back to the job/participation it reprints."""


class MarketingCampaignNotFoundError(DocumentOutputDomainError):
    """Referenced a `MarketingCampaign` id/code that does not exist."""


class MarketingClaimNotAllowedError(DocumentOutputDomainError):
    """A campaign's marketing claim violates the "responsible FOMO" rule
    (SET-13): an urgency/scarcity-style (FOMO) claim with no supporting
    `CampaignRule` — i.e. a claim that would print unconditionally rather
    than being backed by a real, checkable business condition."""


class LabelVariableMissingError(DocumentOutputDomainError):
    """SET-14 "Variables": a label template's declared variable set
    requires a variable the supplied data does not provide, or provides
    with the wrong type."""


class DocumentNumberSequenceNotFoundError(DocumentOutputDomainError):
    """Referenced a `DocumentNumberSequence` id/prefix that does not
    exist."""


class TemplateApprovalSegregationError(DocumentOutputDomainError):
    """SET-1 (§59): the user approving a `DocumentTemplateVersion` is the
    same user who created it — approval requires a second, distinct
    reviewer, same discipline as `feature_flag_approval_policy.
    assert_can_approve`."""
