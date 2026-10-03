"""LoyaltyCardAssignment — el registro de a quién se entregó una tarjeta
preimpresa (master prompt §45).

Inmutable: una tarjeta se asigna una sola vez. Guarda quién la asignó, cuándo,
dónde, por qué y en qué operación.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty_cards.exceptions import InvalidLoyaltyCardError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class LoyaltyCardAssignment:
    id: str
    card_id: str
    loyalty_account_id: str
    membership_id: str
    customer_id: str
    assigned_by_user_id: str
    assignment_reason: str
    branch_id: str
    operation_id: str
    assigned_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        for nombre in ("card_id", "loyalty_account_id", "membership_id", "customer_id",
                       "assigned_by_user_id", "operation_id"):
            if not getattr(self, nombre):
                raise InvalidLoyaltyCardError(f"{nombre} es obligatorio en la asignación")

    @classmethod
    def record(cls, **kwargs) -> "LoyaltyCardAssignment":
        return cls(id=new_uuid(), **kwargs)
