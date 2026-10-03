"""LoyaltyCardPublicToken — the rotatable public-facing QR identifier for a
card (master prompt §32). Deliberately a value distinct from `LoyaltyCard.id`
— rotating it (e.g. after a suspected leak) must never change the card's
own internal identity or its ledger/membership linkage.

LOY-29: the raw token is NEVER stored. The record keeps `token_hash` (to resolve
a scanned QR), `token_prefix` (for support) and `token_version`; the raw token
is derived on demand through a `CardTokenCodec` (HMAC with the installation
secret), so a reprint carries the very same QR without persisting it (§51).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty_cards.enums import LoyaltyCardTokenStatus
from backend.domain.loyalty_cards.exceptions import InvalidLoyaltyCardTokenStateError
from backend.domain.loyalty_cards.value_objects.card_token_codec import (
    DERIVED_TOKEN_VERSION,
    LEGACY_RANDOM_TOKEN_VERSION,
    TOKEN_PREFIX_LENGTH,
    CardTokenCodec,
    hash_public_token,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LoyaltyCardPublicToken:
    id: str
    card_id: str
    token_hash: str
    token_prefix: str
    token_version: int = DERIVED_TOKEN_VERSION
    status: LoyaltyCardTokenStatus = LoyaltyCardTokenStatus.ACTIVE
    created_at: str = field(default_factory=_utcnow)
    rotated_at: str | None = None
    revoked_at: str | None = None

    def __post_init__(self) -> None:
        if not self.card_id:
            raise InvalidLoyaltyCardTokenStateError("card_id es obligatorio")
        if not self.token_hash or len(self.token_hash) != 64:
            raise InvalidLoyaltyCardTokenStateError("token_hash debe ser un SHA-256 hexadecimal")

    @classmethod
    def issue(cls, card_id: str, codec: CardTokenCodec) -> "LoyaltyCardPublicToken":
        token_id = new_uuid()
        raw = codec.derive(token_id, DERIVED_TOKEN_VERSION)
        return cls(id=token_id, card_id=card_id, token_hash=hash_public_token(raw),
                   token_prefix=raw[:TOKEN_PREFIX_LENGTH], token_version=DERIVED_TOKEN_VERSION)

    def raw_token(self, codec: CardTokenCodec) -> str:
        """El token que va dentro del QR, recalculado (nunca leído de la base)."""
        if self.token_version == LEGACY_RANDOM_TOKEN_VERSION:
            raise InvalidLoyaltyCardTokenStateError(
                "Este QR es anterior al formato seguro y no puede reimprimirse: rota el QR")
        raw = codec.derive(self.id, self.token_version)
        if hash_public_token(raw) != self.token_hash:
            raise InvalidLoyaltyCardTokenStateError(
                "El secreto de QR de esta instalación no corresponde al que emitió la tarjeta")
        return raw

    def matches(self, raw_token: str) -> bool:
        return hash_public_token(raw_token) == self.token_hash

    def rotate(self, codec: CardTokenCodec) -> "LoyaltyCardPublicToken":
        """Marks THIS token ROTATED and returns a brand-new ACTIVE token for
        the same card — the old token's string must stop resolving
        immediately, never coexist with the new one."""
        if self.status is not LoyaltyCardTokenStatus.ACTIVE:
            raise InvalidLoyaltyCardTokenStateError(
                f"Solo se rota un token ACTIVE (actual: {self.status.value})")
        self.status = LoyaltyCardTokenStatus.ROTATED
        self.rotated_at = _utcnow()
        return LoyaltyCardPublicToken.issue(self.card_id, codec)

    def revoke(self) -> None:
        if self.status is LoyaltyCardTokenStatus.REVOKED:
            raise InvalidLoyaltyCardTokenStateError("El token ya está revocado")
        self.status = LoyaltyCardTokenStatus.REVOKED
        self.revoked_at = _utcnow()

    def is_usable(self) -> bool:
        return self.status is LoyaltyCardTokenStatus.ACTIVE
