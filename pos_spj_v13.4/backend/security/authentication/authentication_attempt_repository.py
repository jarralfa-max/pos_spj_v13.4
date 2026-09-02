"""AuthenticationAttemptRepository — SHELL-7.

Persists the `AuthenticationAttempt` history `AccountLockoutPolicy`
(SHELL-1) reasons over. Real SQLite persistence, not deferred like SHELL-1
left it — lockout must survive across separate login *attempts* (separate
process invocations of `AuthenticateUserUseCase`, potentially separate app
launches), so an in-memory-only store would reset the failure count on
every restart and defeat the whole point.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from backend.security.sessions.authentication_attempt import AuthenticationAttempt
from backend.shared.ids import new_uuid


@runtime_checkable
class AuthenticationAttemptRepository(Protocol):
    def record(self, attempt: AuthenticationAttempt) -> None: ...

    def recent_for_user(self, user_reference: str, *, limit: int = 20) -> list[AuthenticationAttempt]: ...


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _format_dt(value: datetime) -> str:
    return value.isoformat()


class SqliteAuthenticationAttemptRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def record(self, attempt: AuthenticationAttempt) -> None:
        self._conn.execute(
            "INSERT INTO authentication_attempts "
            "(id, user_reference, workstation_id, success, failure_reason, occurred_at) "
            "VALUES (?,?,?,?,?,?)",
            (
                new_uuid(), attempt.user_reference, attempt.workstation_id,
                1 if attempt.success else 0, attempt.failure_reason,
                _format_dt(attempt.occurred_at),
            ),
        )

    def recent_for_user(self, user_reference: str, *, limit: int = 20) -> list[AuthenticationAttempt]:
        rows = self._conn.execute(
            "SELECT user_reference, workstation_id, success, failure_reason, occurred_at "
            "FROM authentication_attempts WHERE user_reference = ? "
            "ORDER BY occurred_at DESC LIMIT ?",
            (user_reference, limit),
        ).fetchall()
        return [
            AuthenticationAttempt(
                user_reference=row["user_reference"], workstation_id=row["workstation_id"],
                success=bool(row["success"]), failure_reason=row["failure_reason"] or "",
                occurred_at=_parse_dt(row["occurred_at"]),
            )
            for row in rows
        ]


class InMemoryAuthenticationAttemptRepository:
    def __init__(self) -> None:
        self._attempts: list[AuthenticationAttempt] = []

    def record(self, attempt: AuthenticationAttempt) -> None:
        self._attempts.append(attempt)

    def recent_for_user(self, user_reference: str, *, limit: int = 20) -> list[AuthenticationAttempt]:
        matching = [a for a in self._attempts if a.user_reference == user_reference]
        return sorted(matching, key=lambda a: a.occurred_at, reverse=True)[:limit]
