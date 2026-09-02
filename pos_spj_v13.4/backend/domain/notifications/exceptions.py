"""Domain exceptions for the Notifications bounded context — SET-20.
Mirrors backend/domain/integrations/exceptions.py's shape.
"""

from __future__ import annotations


class NotificationsDomainError(Exception):
    """Base for Notifications rule violations."""


class NotificationsInvalidValueError(NotificationsDomainError):
    """A field does not satisfy its validation rule."""


class NotificationAccountNotFoundError(NotificationsDomainError):
    """Referenced a `NotificationAccount` id that does not exist."""


class NotificationTemplateNotFoundError(NotificationsDomainError):
    """Referenced a `NotificationTemplate` id/code that does not exist."""


class TemplateParameterMissingError(NotificationsDomainError):
    """A `NotificationTemplate`'s declared parameters were not all
    supplied — WhatsApp (and every other template-gated channel) rejects
    a send with missing template parameters, so this is caught before
    ever reaching a channel adapter."""


class NotificationRouteNotFoundError(NotificationsDomainError):
    """No active `NotificationRoute` exists for the requested event
    code."""


class NotificationRouteEventCodeOccupiedError(NotificationsDomainError):
    """The target `event_code` already has an active `NotificationRoute`
    — same "explicit deactivate-then-create, never a silent swap"
    discipline `AssignDeviceUseCase` (SET-7) and
    `AssignCampaignPlacementUseCase` (SET-18) already established."""


class NotificationTemplateCodeChannelOccupiedError(NotificationsDomainError):
    """A `NotificationTemplate` with this `code`+`channel` already
    exists — `UNIQUE(code, channel)` — checked explicitly before
    inserting rather than letting a raw `IntegrityError` reach the UI."""
