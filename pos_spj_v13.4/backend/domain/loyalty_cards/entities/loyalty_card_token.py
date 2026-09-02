"""LoyaltyCardPublicToken — the rotatable public-facing QR identifier for a
card (master prompt §32). Deliberately a value distinct from `LoyaltyCard.id`
— rotating it (e.g. after a suspected leak) must never change the card's
own internal identity or its ledger/membership linkage."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty_cards.enums import LoyaltyCardTokenStatus
from backend.domain.loyalty_cards.exceptions import InvalidLoyaltyCardTokenStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _generate_token() -> str:
    return secrets.token_urlsafe(24)


@dataclass(slots=True)
class LoyaltyCardPublicToken:
    id: str
    card_id: str
    token: str
    status: LoyaltyCardTokenStatus = LoyaltyCardTokenStatus.ACTIVE
    created_at: str = field(default_factory=_utcnow)
    rotated_at: str | None = None
    revoked_at: str | None = None

    def __post_init__(self) -> None:
        if not self.card_id:
            raise InvalidLoyaltyCardTokenStateError("card_id es obligatorio")
        if not self.token or not self.token.strip():
            raise InvalidLoyaltyCardTokenStateError("token es obligatorio")

    @classmethod
    def issue(cls, card_id: str) -> "LoyaltyCardPublicToken":
        return cls(id=new_uuid(), card_id=card_id, token=_generate_token())

    def rotate(self) -> "LoyaltyCardPublicToken":
        """Marks THIS token ROTATED and returns a brand-new ACTIVE token for
        the same card — the old token's string must stop resolving
        immediately, never coexist with the new one."""
        if self.status is not LoyaltyCardTokenStatus.ACTIVE:
            raise InvalidLoyaltyCardTokenStateError(
                f"Solo se rota un token ACTIVE (actual: {self.status.value})")
        self.status = LoyaltyCardTokenStatus.ROTATED
        self.rotated_at = _utcnow()
        return LoyaltyCardPublicToken.issue(self.card_id)

    def revoke(self) -> None:
        if self.status is LoyaltyCardTokenStatus.REVOKED:
            raise InvalidLoyaltyCardTokenStateError("El token ya está revocado")
        self.status = LoyaltyCardTokenStatus.REVOKED
        self.revoked_at = _utcnow()

    def is_usable(self) -> bool:
        return self.status is LoyaltyCardTokenStatus.ACTIVE
