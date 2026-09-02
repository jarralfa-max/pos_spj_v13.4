"""Domain exceptions for the Customer Display bounded context — SET-17.
Mirrors backend/domain/document_output/exceptions.py's shape.
"""

from __future__ import annotations


class CustomerDisplayDomainError(Exception):
    """Base for Customer Display rule violations."""


class CustomerDisplayInvalidValueError(CustomerDisplayDomainError):
    """A field does not satisfy its validation rule."""


class CustomerDisplayNotFoundError(CustomerDisplayDomainError):
    """Referenced a `CustomerDisplay` id that does not exist."""


class DisplayLayoutNotFoundError(CustomerDisplayDomainError):
    """No active `DisplayLayout` exists for the requested mode."""


class ContentCampaignTransitionNotAllowedError(CustomerDisplayDomainError):
    """The `ContentCampaign` is not in a state that allows the requested
    approval-lifecycle transition."""


class ContentCampaignApprovalSegregationError(CustomerDisplayDomainError):
    """Whoever created a `ContentCampaign` may not also approve it —
    same §59 segregation-of-duties rule the SET-1 repegado round added to
    `DocumentTemplateVersion.approve()`; this entity mirrors that one's
    shape but the check itself was never copied over until now."""


class CampaignPlacementNotAllowedError(CustomerDisplayDomainError):
    """A `ContentCampaign` may not be assigned to an `AdvertisingSlot` —
    e.g. the campaign has not reached ACTIVE status yet (SET-18
    "Approval" gating SET-18 "Placements": unapproved/unreviewed content
    must never reach the screen)."""


class AssignmentAlreadyInactiveError(CustomerDisplayDomainError):
    """Attempted to unassign a `CampaignPlacement` that is already
    inactive."""


class CampaignPlacementSlotOccupiedError(CustomerDisplayDomainError):
    """The target `AdvertisingSlot` already has an active
    `CampaignPlacement` — same "explicit unassign-then-assign, never a
    silent swap" discipline `AssignDeviceUseCase` (SET-7) already
    established for `WorkstationDeviceAssignment`."""
