from datetime import datetime, timedelta, timezone

import pytest

from backend.security.credentials.password_hasher import Argon2idPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.recovery.account_recovery_service import AccountRecoveryService
from backend.security.recovery.errors import RecoveryTokenExpiredError, RecoveryTokenInvalidError
from backend.security.recovery.recovery_token_repository import InMemoryRecoveryTokenRepository

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def service() -> AccountRecoveryService:
    return AccountRecoveryService(
        token_repository=InMemoryRecoveryTokenRepository(),
        password_hasher=Argon2idPasswordHasher(),
        password_policy=PasswordPolicy(),
        token_ttl_seconds=900,
    )


def test_begin_recovery_returns_raw_token(service):
    raw_token = service.begin_recovery("juan", now=T0)
    assert isinstance(raw_token, str)
    assert len(raw_token) >= 32


def test_complete_recovery_with_valid_token_returns_new_hash(service):
    raw_token = service.begin_recovery("juan", now=T0)
    result = service.complete_recovery(raw_token, "Correct-Horse-9!", now=T0 + timedelta(seconds=5))
    assert result.user_reference == "juan"
    assert result.new_password_hash.startswith("$argon2id$")


def test_complete_recovery_with_unknown_token_raises_invalid(service):
    with pytest.raises(RecoveryTokenInvalidError):
        service.complete_recovery("not-a-real-token", "Correct-Horse-9!", now=T0)


def test_complete_recovery_twice_with_same_token_raises_invalid(service):
    raw_token = service.begin_recovery("juan", now=T0)
    service.complete_recovery(raw_token, "Correct-Horse-9!", now=T0 + timedelta(seconds=5))
    with pytest.raises(RecoveryTokenInvalidError):
        service.complete_recovery(raw_token, "Another-Strong-9!", now=T0 + timedelta(seconds=10))


def test_complete_recovery_after_expiry_raises_expired(service):
    raw_token = service.begin_recovery("juan", now=T0)
    with pytest.raises(RecoveryTokenExpiredError):
        service.complete_recovery(raw_token, "Correct-Horse-9!", now=T0 + timedelta(seconds=901))


def test_complete_recovery_rejects_weak_password(service):
    raw_token = service.begin_recovery("juan", now=T0)
    with pytest.raises(Exception):
        service.complete_recovery(raw_token, "weak", now=T0 + timedelta(seconds=1))


def test_new_recovery_request_invalidates_previous_token(service):
    first_token = service.begin_recovery("juan", now=T0)
    second_token = service.begin_recovery("juan", now=T0 + timedelta(seconds=1))

    with pytest.raises(RecoveryTokenInvalidError):
        service.complete_recovery(first_token, "Correct-Horse-9!", now=T0 + timedelta(seconds=2))

    # the newer token still works
    result = service.complete_recovery(second_token, "Correct-Horse-9!", now=T0 + timedelta(seconds=3))
    assert result.user_reference == "juan"


def test_begin_recovery_rejects_empty_user_reference(service):
    with pytest.raises(ValueError):
        service.begin_recovery("")


def test_audit_sink_receives_canonical_events():
    events = []
    service = AccountRecoveryService(
        token_repository=InMemoryRecoveryTokenRepository(),
        password_hasher=Argon2idPasswordHasher(),
        password_policy=PasswordPolicy(),
        audit_sink=lambda event, payload: events.append((event, payload)),
    )
    raw_token = service.begin_recovery("juan", now=T0)
    service.complete_recovery(raw_token, "Correct-Horse-9!", now=T0 + timedelta(seconds=1))

    event_names = [e for e, _ in events]
    assert "ACCOUNT_RECOVERY_REQUESTED" in event_names
    assert "ACCOUNT_RECOVERY_COMPLETED" in event_names
    # never leaks the raw token or password through the audit sink
    for _, payload in events:
        assert raw_token not in str(payload)
        assert "Correct-Horse-9!" not in str(payload)
