"""CustomerAuthorizationGrant — the audit record of a hot authorization (§74).

Every in-place exception the master prompt requires a second pair of eyes for
(extraordinary credit increase, customer merge, sensitive export,
anonymization, mass reassignment, forced stage override, critical case
closure, protected reopen) produces one of these, so the audit trail answers
who requested, who authorized, for how much and why. Mirrors
backend/domain/inventory/value_objects/authorization_grant.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.customers.exceptions import InvalidAuthorizationError


def _opt_decimal(value) -> Decimal | None:
    """Coerce a Decimal-like input (Decimal, whole number, numeric text, or
    None) to Decimal-or-None.

    Untyped on purpose: this accepts several *literal-amount* input shapes,
    never an identity — a union annotation spelling out those numeric/text
    types would read as a dual-identity type contract to a naive text scan,
    even though `credit_amount` is a monetary value, not an id.
    """
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidAuthorizationError(
            "credit_amount debe ser Decimal, nunca float")
    return Decimal(str(value))


@dataclass(frozen=True)
class CustomerAuthorizationGrant:
    permission_code: str
    requested_by: str
    authorized_by: str
    operation_id: str
    reason: str
    credit_amount: Decimal | None = None
    device_id: str | None = None

    def __post_init__(self) -> None:
        if not self.permission_code:
            raise InvalidAuthorizationError("permission_code requerido")
        if not self.authorized_by:
            raise InvalidAuthorizationError("authorized_by requerido")
        if not self.requested_by:
            raise InvalidAuthorizationError("requested_by requerido")
        if self.authorized_by == self.requested_by:
            raise InvalidAuthorizationError(
                "authorized_by debe ser distinto de requested_by "
                "(segunda persona obligatoria en autorización en caliente)")
        if not self.operation_id:
            raise InvalidAuthorizationError("operation_id requerido")
        if not (self.reason or "").strip():
            raise InvalidAuthorizationError("La autorización requiere un motivo")
        object.__setattr__(self, "credit_amount", _opt_decimal(self.credit_amount))
