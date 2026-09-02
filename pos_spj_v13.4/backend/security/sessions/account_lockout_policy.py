"""AccountLockoutPolicy — SHELL-1 security foundation.

Pure decision logic for brute-force lockout: given the recent
`AuthenticationAttempt` history for a user, decide whether a new attempt is
currently blocked, and for how much longer.

No storage, no clock side effects — the caller owns where attempts are
persisted (in-memory rate limiter today, an `authentication_attempts` table
in a later phase) and passes the relevant window of attempts in. This keeps
the policy trivially testable and reusable from both contexts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.security.sessions.authentication_attempt import AuthenticationAttempt
from backend.security.sessions.errors import AccountLockedError


class AccountLockoutPolicy:
    def __init__(self, *, failed_attempt_limit: int = 5, lockout_duration_seconds: int = 900) -> None:
        if failed_attempt_limit < 1:
            raise ValueError("failed_attempt_limit debe ser >= 1.")
        if lockout_duration_seconds < 0:
            raise ValueError("lockout_duration_seconds no puede ser negativo.")
        self.failed_attempt_limit = failed_attempt_limit
        self.lockout_duration_seconds = lockout_duration_seconds

    def locked_until(
        self, attempts: list[AuthenticationAttempt], *, now: datetime | None = None
    ) -> datetime | None:
        """Return the moment the lockout lifts, or None if not currently locked.

        Only consecutive trailing failures count: a successful attempt clears
        the streak, matching "reset counter on successful login" semantics.
        """
        now = now or datetime.now(timezone.utc)
        streak = self._trailing_failure_streak(attempts)
        if len(streak) < self.failed_attempt_limit:
            return None
        last_failure_at = streak[-1].occurred_at
        unlock_at = last_failure_at + timedelta(seconds=self.lockout_duration_seconds)
        return unlock_at if unlock_at > now else None

    def is_locked_out(
        self, attempts: list[AuthenticationAttempt], *, now: datetime | None = None
    ) -> bool:
        return self.locked_until(attempts, now=now) is not None

    def require_not_locked_out(
        self, attempts: list[AuthenticationAttempt], *, now: datetime | None = None
    ) -> None:
        now = now or datetime.now(timezone.utc)
        unlock_at = self.locked_until(attempts, now=now)
        if unlock_at is not None:
            raise AccountLockedError(retry_after_seconds=int((unlock_at - now).total_seconds()))

    @staticmethod
    def _trailing_failure_streak(
        attempts: list[AuthenticationAttempt],
    ) -> list[AuthenticationAttempt]:
        ordered = sorted(attempts, key=lambda a: a.occurred_at)
        streak: list[AuthenticationAttempt] = []
        for attempt in reversed(ordered):
            if attempt.success:
                break
            streak.append(attempt)
        return list(reversed(streak))


DEFAULT_ACCOUNT_LOCKOUT_POLICY = AccountLockoutPolicy()
