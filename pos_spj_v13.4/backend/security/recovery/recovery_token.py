"""RecoveryToken — SHELL-1 security foundation.

A recovery token is a single-use, expiring, high-entropy secret handed to a
user to prove they control the recovery channel (email/SMS) for an account.
Unlike a password, it is never chosen by a human and is generated with
`secrets.token_urlsafe` (256 bits) — so it is hashed with a fast
cryptographic digest (SHA-256) rather than Argon2id: brute-forcing 256 bits
of entropy is infeasible regardless of hash speed, and a fast, unsalted
digest is what lets `RecoveryTokenRepository.find_by_hash()` look a token up
in O(1) instead of iterating every outstanding token to run a slow KDF
against each one — the same trade-off Django and Rails make for reset
tokens. The raw token is returned to the caller exactly once (at issuance)
and never stored or logged anywhere; only its hash persists.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.shared.ids import new_uuid


def generate_raw_token() -> str:
    """A fresh, URL-safe, 256-bit recovery token. Shown to the user once."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    if not raw_token:
        raise ValueError("raw_token no puede estar vacío.")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RecoveryToken:
    token_id: str
    user_reference: str
    token_hash: str
    issued_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    @classmethod
    def issue(
        cls,
        user_reference: str,
        *,
        raw_token: str,
        ttl_seconds: int = 900,
        issued_at: datetime | None = None,
    ) -> "RecoveryToken":
        if not user_reference:
            raise ValueError("user_reference no puede estar vacío.")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds debe ser positivo.")
        issued_at = issued_at or datetime.now(timezone.utc)
        return cls(
            token_id=new_uuid(),
            user_reference=user_reference,
            token_hash=hash_token(raw_token),
            issued_at=issued_at,
            expires_at=issued_at.fromtimestamp(
                issued_at.timestamp() + ttl_seconds, tz=timezone.utc
            ),
        )

    def is_used(self) -> bool:
        return self.used_at is not None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now >= self.expires_at

    def mark_used(self, *, used_at: datetime | None = None) -> "RecoveryToken":
        """Consume the token — either because it completed a recovery flow,
        or because a newer request superseded it (see `invalidate()`). Once
        consumed a token can never be presented again."""
        if self.is_used():
            raise ValueError(f"El token {self.token_id} ya fue utilizado.")
        return RecoveryToken(
            token_id=self.token_id,
            user_reference=self.user_reference,
            token_hash=self.token_hash,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
            used_at=used_at or datetime.now(timezone.utc),
        )

    def invalidate(self, *, at: datetime | None = None) -> "RecoveryToken":
        """Consume the token because a newer recovery request superseded it.
        Semantically identical to `mark_used()` — kept as a distinct name so
        call sites document *why* the token was consumed."""
        return self.mark_used(used_at=at)
