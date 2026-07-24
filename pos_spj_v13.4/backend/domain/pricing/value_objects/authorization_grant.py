"""PricingAuthorizationGrant — the audit record of a hot authorization (PRC-1).

Every in-place pricing exception (selling below the minimum price, approving one's
own price list, activating a list out of band) produces one of these so the audit
trail answers who requested, who authorized and why. Immutable domain record;
persistence lands with the pricing schema (PRC-3).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.pricing.exceptions import InvalidAuthorizationError


@dataclass(frozen=True)
class PricingAuthorizationGrant:
    permission_code: str
    requested_by: str
    authorized_by: str
    operation_id: str
    reason: str
    entity_id: str | None = None
    device_id: str | None = None

    def __post_init__(self) -> None:
        if not self.permission_code:
            raise InvalidAuthorizationError("permission_code requerido")
        if not self.authorized_by:
            raise InvalidAuthorizationError("authorized_by requerido")
        if not self.requested_by:
            raise InvalidAuthorizationError("requested_by requerido")
        if not self.operation_id:
            raise InvalidAuthorizationError("operation_id requerido")
        if not (self.reason or "").strip():
            raise InvalidAuthorizationError("La autorización requiere un motivo")
