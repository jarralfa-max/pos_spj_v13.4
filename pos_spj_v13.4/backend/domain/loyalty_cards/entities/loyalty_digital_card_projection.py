"""LoyaltyDigitalCardProjection — a read-optimized snapshot of a DIGITAL
card for display in a wallet/app screen (master prompt §48).

A projection, not a source of truth: `display_fields` is a denormalized
snapshot (customer name, membership tier, points balance, ...) resolved and
supplied by the caller — this entity never reaches into Customers/Loyalty's
own ledger itself (same bounded-context-isolation discipline as every other
cross-context value in this pipeline). `refresh()` replaces the whole
snapshot; there is no partial-field update, so a stale projection can never
mix old and new values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty_cards.exceptions import InvalidDigitalCardProjectionError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LoyaltyDigitalCardProjection:
    id: str
    card_id: str
    customer_id: str
    card_number: str
    token_id: str
    display_fields: dict[str, str] = field(default_factory=dict)
    last_refreshed_at: str = field(default_factory=_utcnow)
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.card_id:
            raise InvalidDigitalCardProjectionError("card_id es obligatorio")
        if not self.customer_id:
            raise InvalidDigitalCardProjectionError("customer_id es obligatorio")
        if not self.card_number or not self.card_number.strip():
            raise InvalidDigitalCardProjectionError("card_number es obligatorio")
        if not self.token_id or not self.token_id.strip():
            raise InvalidDigitalCardProjectionError("token_id es obligatorio")

    @classmethod
    def create(cls, card_id: str, customer_id: str, card_number: str, token_id: str,
               *, display_fields: dict[str, str] | None = None) -> "LoyaltyDigitalCardProjection":
        return cls(id=new_uuid(), card_id=card_id, customer_id=customer_id,
                    card_number=card_number, token_id=token_id,
                    display_fields=dict(display_fields or {}))

    def refresh(self, display_fields: dict[str, str], *, token_id: str | None = None) -> None:
        """Replaces the entire display snapshot — never merges partial
        updates, so a caller cannot accidentally leave stale fields mixed
        with fresh ones."""
        self.display_fields = dict(display_fields)
        if token_id is not None:
            if not token_id.strip():
                raise InvalidDigitalCardProjectionError("token_id no puede quedar vacío")
            self.token_id = token_id
        self.last_refreshed_at = _utcnow()
