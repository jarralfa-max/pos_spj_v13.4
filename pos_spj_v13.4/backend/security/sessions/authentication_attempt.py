"""AuthenticationAttempt — SHELL-1 security foundation.

Immutable record of a single login attempt, success or failure. Pure data —
persistence (an `authentication_attempts` table) is an infrastructure
concern for a later phase; `AccountLockoutPolicy` only needs the sequence of
attempts to make a lockout decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class AuthenticationAttempt:
    user_reference: str
    workstation_id: str
    success: bool
    occurred_at: datetime
    failure_reason: str = ""

    @classmethod
    def failure(
        cls, user_reference: str, *, workstation_id: str = "", reason: str = "",
        occurred_at: datetime | None = None,
    ) -> "AuthenticationAttempt":
        return cls(
            user_reference=user_reference,
            workstation_id=workstation_id,
            success=False,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            failure_reason=reason,
        )

    @classmethod
    def succeeded(
        cls, user_reference: str, *, workstation_id: str = "",
        occurred_at: datetime | None = None,
    ) -> "AuthenticationAttempt":
        return cls(
            user_reference=user_reference,
            workstation_id=workstation_id,
            success=True,
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )
