"""Domain exceptions for the Device Management bounded context — SET-7.
Mirrors backend/domain/settings/exceptions.py's shape.
"""

from __future__ import annotations


class DeviceManagementDomainError(Exception):
    """Base for Device Management rule violations."""


class DeviceInvalidValueError(DeviceManagementDomainError):
    """A field does not satisfy its validation rule (bad connection
    profile, secret-looking key in connection_parameters, invalid
    capability parameters, ...)."""


class DeviceNotFoundError(DeviceManagementDomainError):
    """Referenced a `Device` id/code that does not exist."""


class DeviceProfileNotFoundError(DeviceManagementDomainError):
    """Referenced a `DeviceProfile` id that does not exist."""


class DeviceTransitionNotAllowedError(DeviceManagementDomainError):
    """The device is not in a state that allows the requested transition
    (retirement is terminal, same as Workstation's)."""


class DeviceAssignmentConflictError(DeviceManagementDomainError):
    """A workstation already has an active device assigned to this role
    (§20/§62 — at most one active device per (workstation, role))."""


class DeviceAssignmentNotFoundError(DeviceManagementDomainError):
    """Referenced a `WorkstationDeviceAssignment` id that does not
    exist."""


class DeviceAssignmentRoleNotCompatibleError(DeviceManagementDomainError):
    """The requested `AssignmentRole` cannot point at this device's
    `DeviceType` (e.g. assigning a SCALE to CASH_DRAWER)."""


class InvalidPrinterProfileError(DeviceManagementDomainError):
    """A `DeviceProfile` fails printer-specific validation: wrong
    device_type, non-canonical paper_profile, or an unrecognized
    protocol (§23 — never assume every printer is ESC/POS)."""


class PrintRouteNotFoundError(DeviceManagementDomainError):
    """No active `PrintRoute` matches the requested document_type and
    routing context (§25)."""


class PrintRouteConflictError(DeviceManagementDomainError):
    """A `PrintRoute` already exists for the exact same (document_type,
    scope) combination (§25/§62 — schema's unique index enforces this;
    this is the clean domain-level check before it's attempted)."""


class NoAvailablePrinterError(DeviceManagementDomainError):
    """Neither a route's primary printer nor any of its fallback chain
    is available (§25 failover exhausted)."""


class InvalidScaleProfileError(DeviceManagementDomainError):
    """A `DeviceProfile` fails scale-specific validation: wrong
    device_type, unrecognized protocol, or missing the WEIGH
    capability (§22)."""


class InvalidReaderProfileError(DeviceManagementDomainError):
    """A `DeviceProfile` fails reader-specific validation: wrong
    device_type, or missing the scan capability its type implies."""


class InvalidCashDrawerProfileError(DeviceManagementDomainError):
    """A `DeviceProfile` fails cash-drawer-specific validation: wrong
    device_type, or missing the DRAWER_PULSE capability."""


class InvalidPaymentTerminalProfileError(DeviceManagementDomainError):
    """A `DeviceProfile` fails payment-terminal-specific validation:
    wrong device_type, or none of the payment capabilities declared."""


class CashDrawerOpeningNotAuthorizedError(DeviceManagementDomainError):
    """§60/legacy `CASH_DRAWER_OPEN_WITHOUT_SALE`: opening a drawer with
    no linked sale requires an explicit reason — this request doesn't
    have one."""
