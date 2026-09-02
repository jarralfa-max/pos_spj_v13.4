from datetime import datetime, timedelta, timezone

import pytest

from backend.security.credentials.password_hasher import Argon2idPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.recovery.account_recovery_service import AccountRecoveryService
from backend.security.recovery.begin_account_recovery_use_case import BeginAccountRecoveryUseCase
from backend.security.recovery.complete_account_recovery_use_case import (
    CompleteAccountRecoveryUseCase,
)
from backend.security.recovery.recovery_token_repository import InMemoryRecoveryTokenRepository

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def service() -> AccountRecoveryService:
    return AccountRecoveryService(
        token_repository=InMemoryRecoveryTokenRepository(),
        password_hasher=Argon2idPasswordHasher(),
        password_policy=PasswordPolicy(),
    )


def test_begin_then_complete_round_trip(service):
    begin = BeginAccountRecoveryUseCase(service)
    complete = CompleteAccountRecoveryUseCase(service)

    raw_token = begin.execute("juan")
    result = complete.execute(raw_token, "Correct-Horse-9!")

    assert result.user_reference == "juan"
    assert result.new_password_hash.startswith("$argon2id$")
