"""AccountRecoveryService — SHELL-1 security foundation.

Orchestrates the "forgot my password" flow without touching the database
directly: it depends on a `RecoveryTokenRepository` port for persistence, a
`PasswordHasher` to hash the new password, and a `PasswordPolicy` to reject
weak replacements. Callers own actually persisting the new password hash —
this service returns it rather than writing to `usuarios` itself, keeping
schema/UOW ownership with the caller (per "servicios no deben crear ni
alterar schema").

No master password, ever: `complete_recovery()` is the only way to set a
new password, and it requires a valid, unused, unexpired token.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from backend.security.audit.security_events import (
    ACCOUNT_RECOVERY_COMPLETED as EVENT_ACCOUNT_RECOVERY_COMPLETED,
    ACCOUNT_RECOVERY_REQUESTED as EVENT_ACCOUNT_RECOVERY_REQUESTED,
)
from backend.security.credentials.password_hasher import PasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.recovery.errors import RecoveryTokenExpiredError, RecoveryTokenInvalidError
from backend.security.recovery.recovery_token import RecoveryToken, generate_raw_token, hash_token
from backend.security.recovery.recovery_token_repository import RecoveryTokenRepository

AuditSink = Callable[[str, dict], None]


@dataclass(frozen=True)
class RecoveryCompletionResult:
    user_reference: str
    new_password_hash: str


class AccountRecoveryService:
    def __init__(
        self,
        *,
        token_repository: RecoveryTokenRepository,
        password_hasher: PasswordHasher,
        password_policy: PasswordPolicy,
        token_ttl_seconds: int = 900,
        audit_sink: Optional[AuditSink] = None,
    ) -> None:
        self._tokens = token_repository
        self._hasher = password_hasher
        self._policy = password_policy
        self._ttl_seconds = token_ttl_seconds
        self._audit = audit_sink or (lambda event, payload: None)

    def begin_recovery(self, user_reference: str, *, now: datetime | None = None) -> str:
        """Issue a new recovery token, superseding any still-outstanding ones
        for this user. Returns the raw token — the only time it exists in
        plaintext; deliver it out-of-band (email/SMS), never log it."""
        user_reference = (user_reference or "").strip()
        if not user_reference:
            raise ValueError("user_reference no puede estar vacío.")

        for outstanding in self._tokens.find_active_for_user(user_reference):
            self._tokens.replace(outstanding.invalidate(at=now))

        raw_token = generate_raw_token()
        token = RecoveryToken.issue(
            user_reference, raw_token=raw_token, ttl_seconds=self._ttl_seconds,
            issued_at=now,
        )
        self._tokens.save(token)
        self._audit(EVENT_ACCOUNT_RECOVERY_REQUESTED, {"user_reference": user_reference})
        return raw_token

    def complete_recovery(
        self, raw_token: str, new_password: str, *, now: datetime | None = None
    ) -> RecoveryCompletionResult:
        """Validate the token and return the hash for the new password. The
        caller persists it (and the token-consumed state) inside its own
        transaction."""
        token = self._tokens.find_by_hash(hash_token(raw_token)) if raw_token else None
        if token is None or token.is_used():
            # Same generic error whether the token is unknown or already
            # consumed — never reveal which, to avoid leaking account state.
            raise RecoveryTokenInvalidError("El código de recuperación no es válido.")
        if token.is_expired(now=now):
            raise RecoveryTokenExpiredError("El código de recuperación ha expirado.")

        self._policy.validate(new_password, username=token.user_reference)
        new_hash = self._hasher.hash(new_password)

        self._tokens.replace(token.mark_used(used_at=now))
        self._audit(
            EVENT_ACCOUNT_RECOVERY_COMPLETED, {"user_reference": token.user_reference}
        )
        return RecoveryCompletionResult(
            user_reference=token.user_reference, new_password_hash=new_hash
        )
