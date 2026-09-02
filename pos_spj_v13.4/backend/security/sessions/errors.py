"""Canonical session/lockout errors — SHELL-1 security foundation."""
from __future__ import annotations


class AccountLockedError(RuntimeError):
    """Raised when an authentication attempt is rejected because the account
    is currently under a lockout window. Carries `retry_after_seconds` so
    callers can show a countdown instead of a generic message."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Cuenta temporalmente bloqueada. Intente de nuevo en "
            f"{retry_after_seconds}s."
        )
