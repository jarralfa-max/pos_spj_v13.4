"""ProductAuthorizationGrant — the audit record of a hot authorization (§39, §48).

Every in-place exception in Products (activating an incomplete product, approving
a classification change, forcing an over-tolerance yield, importing external data
without the standard review) produces one of these so the audit trail answers who
requested, who authorized and why. It is an immutable domain record; persistence
lands with the products schema (PROD-4).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.products.exceptions import InvalidAuthorizationError


@dataclass(frozen=True)
class ProductAuthorizationGrant:
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
