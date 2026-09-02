"""RecoveryTokenRepository port — SHELL-1/SHELL-7 security foundation.

SHELL-1 shipped this as a protocol plus an in-memory reference
implementation, deferring real persistence until something actually put
`AccountRecoveryService` behind a UI. SHELL-7 does that (LoginWindow's
"forgot password" flow), so `SqliteRecoveryTokenRepository` now backs it for
real — a token has to survive the gap between "user requests recovery" and
"user clicks the emailed link a few minutes later," which in-memory storage
obviously can't. Table created by migration 207
(`backend/infrastructure/db/schema/account_recovery_schema.py`).
`InMemoryRecoveryTokenRepository` stays for tests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from backend.security.recovery.recovery_token import RecoveryToken


@runtime_checkable
class RecoveryTokenRepository(Protocol):
    def save(self, token: RecoveryToken) -> None: ...

    def find_by_hash(self, token_hash: str) -> RecoveryToken | None: ...

    def find_active_for_user(self, user_reference: str) -> list[RecoveryToken]:
        """Outstanding (unused, unexpired-or-not) tokens for a user — used to
        invalidate siblings when a new recovery request supersedes them."""
        ...

    def replace(self, token: RecoveryToken) -> None:
        """Persist a mutated token (e.g. after `mark_used()`)."""
        ...


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _format_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class SqliteRecoveryTokenRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def save(self, token: RecoveryToken) -> None:
        self._conn.execute(
            "INSERT INTO account_recovery_tokens "
            "(token_id, user_reference, token_hash, issued_at, expires_at, used_at) "
            "VALUES (?,?,?,?,?,?)",
            (
                token.token_id, token.user_reference, token.token_hash,
                _format_dt(token.issued_at), _format_dt(token.expires_at), _format_dt(token.used_at),
            ),
        )

    def find_by_hash(self, token_hash: str) -> RecoveryToken | None:
        row = self._conn.execute(
            "SELECT token_id, user_reference, token_hash, issued_at, expires_at, used_at "
            "FROM account_recovery_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        return self._row_to_token(row) if row else None

    def find_active_for_user(self, user_reference: str) -> list[RecoveryToken]:
        rows = self._conn.execute(
            "SELECT token_id, user_reference, token_hash, issued_at, expires_at, used_at "
            "FROM account_recovery_tokens WHERE user_reference = ? AND used_at IS NULL",
            (user_reference,),
        ).fetchall()
        return [self._row_to_token(row) for row in rows]

    def replace(self, token: RecoveryToken) -> None:
        self._conn.execute(
            "UPDATE account_recovery_tokens SET used_at = ? WHERE token_id = ?",
            (_format_dt(token.used_at), token.token_id),
        )

    @staticmethod
    def _row_to_token(row) -> RecoveryToken:
        return RecoveryToken(
            token_id=row["token_id"], user_reference=row["user_reference"],
            token_hash=row["token_hash"], issued_at=_parse_dt(row["issued_at"]),
            expires_at=_parse_dt(row["expires_at"]),
            used_at=_parse_dt(row["used_at"]) if row["used_at"] else None,
        )


class InMemoryRecoveryTokenRepository:
    """Reference `RecoveryTokenRepository` — process-local dict, not durable.
    Suitable for tests and for wiring before a real persistence adapter
    exists."""

    def __init__(self) -> None:
        self._by_hash: dict[str, RecoveryToken] = {}

    def save(self, token: RecoveryToken) -> None:
        self._by_hash[token.token_hash] = token

    def find_by_hash(self, token_hash: str) -> RecoveryToken | None:
        return self._by_hash.get(token_hash)

    def find_active_for_user(self, user_reference: str) -> list[RecoveryToken]:
        return [
            t for t in self._by_hash.values()
            if t.user_reference == user_reference and not t.is_used()
        ]

    def replace(self, token: RecoveryToken) -> None:
        self._by_hash[token.token_hash] = token
