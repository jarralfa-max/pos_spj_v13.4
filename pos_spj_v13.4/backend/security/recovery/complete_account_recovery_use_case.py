"""CompleteAccountRecoveryUseCase — SHELL-1 security foundation."""
from __future__ import annotations

from backend.security.recovery.account_recovery_service import (
    AccountRecoveryService,
    RecoveryCompletionResult,
)


class CompleteAccountRecoveryUseCase:
    def __init__(self, recovery_service: AccountRecoveryService) -> None:
        self._service = recovery_service

    def execute(self, raw_token: str, new_password: str) -> RecoveryCompletionResult:
        """Returns the new password hash for the caller to persist inside
        its own transaction, alongside marking the token consumed."""
        return self._service.complete_recovery(raw_token, new_password)
