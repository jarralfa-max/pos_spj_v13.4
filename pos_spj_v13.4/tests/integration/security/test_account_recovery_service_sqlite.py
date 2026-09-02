"""AccountRecoveryService (SHELL-1) against the real SqliteRecoveryTokenRepository
(SHELL-7) — SHELL-1's own tests only exercised the in-memory reference repo.
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.security.credentials.password_hasher import Argon2idPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.recovery.account_recovery_service import AccountRecoveryService
from backend.security.recovery.errors import RecoveryTokenInvalidError
from backend.security.recovery.recovery_token_repository import SqliteRecoveryTokenRepository
from tests.integration._born_clean_db import make_db

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _service(conn) -> AccountRecoveryService:
    return AccountRecoveryService(
        token_repository=SqliteRecoveryTokenRepository(conn),
        password_hasher=Argon2idPasswordHasher(),
        password_policy=PasswordPolicy(),
    )


def test_begin_and_complete_recovery_against_real_sqlite_repository():
    conn = make_db()
    service = _service(conn)
    raw_token = service.begin_recovery("juan", now=T0)
    conn.commit()

    result = service.complete_recovery(raw_token, "Correct-Horse-9!", now=T0 + timedelta(seconds=5))
    assert result.user_reference == "juan"
    assert result.new_password_hash.startswith("$argon2id$")


def test_token_survives_a_fresh_repository_instance_against_the_same_connection():
    # Simulates the process restarting between "request" and "complete" —
    # the whole reason this needed real persistence in the first place.
    conn = make_db()
    service_a = _service(conn)
    raw_token = service_a.begin_recovery("juan", now=T0)
    conn.commit()

    service_b = AccountRecoveryService(
        token_repository=SqliteRecoveryTokenRepository(conn),  # fresh repository instance
        password_hasher=Argon2idPasswordHasher(),
        password_policy=PasswordPolicy(),
    )
    result = service_b.complete_recovery(raw_token, "Correct-Horse-9!", now=T0 + timedelta(seconds=5))
    assert result.user_reference == "juan"


def test_token_cannot_be_reused_against_real_repository():
    conn = make_db()
    service = _service(conn)
    raw_token = service.begin_recovery("juan", now=T0)
    conn.commit()
    service.complete_recovery(raw_token, "Correct-Horse-9!", now=T0 + timedelta(seconds=1))
    conn.commit()

    with pytest.raises(RecoveryTokenInvalidError):
        service.complete_recovery(raw_token, "Another-Strong-9!", now=T0 + timedelta(seconds=2))
