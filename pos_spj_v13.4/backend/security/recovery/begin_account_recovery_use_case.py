"""BeginAccountRecoveryUseCase — SHELL-1 security foundation.

Thin entry point over `AccountRecoveryService.begin_recovery()` — kept as
its own use case (rather than callers reaching into the service directly)
so a future UI/API layer has one narrow, permission-checkable seam per the
"toda operación crítica debe pasar por Use Case" rule.
"""
from __future__ import annotations

from backend.security.recovery.account_recovery_service import AccountRecoveryService


class BeginAccountRecoveryUseCase:
    def __init__(self, recovery_service: AccountRecoveryService) -> None:
        self._service = recovery_service

    def execute(self, user_reference: str) -> str:
        """Returns the raw recovery token to hand to the delivery channel
        (email/SMS) — never persisted, never logged."""
        return self._service.begin_recovery(user_reference)
