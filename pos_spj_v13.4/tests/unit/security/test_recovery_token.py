from datetime import datetime, timedelta, timezone

import pytest

from backend.security.recovery.recovery_token import RecoveryToken, generate_raw_token, hash_token

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_generate_raw_token_is_high_entropy_and_unique():
    a = generate_raw_token()
    b = generate_raw_token()
    assert a != b
    assert len(a) >= 32


def test_hash_token_is_deterministic():
    raw = "some-raw-token-value"
    assert hash_token(raw) == hash_token(raw)


def test_hash_token_differs_for_different_inputs():
    assert hash_token("token-a") != hash_token("token-b")


def test_hash_token_rejects_empty():
    with pytest.raises(ValueError):
        hash_token("")


def test_issue_creates_unused_unexpired_token():
    raw = generate_raw_token()
    token = RecoveryToken.issue("juan", raw_token=raw, ttl_seconds=900, issued_at=T0)
    assert token.is_used() is False
    assert token.is_expired(now=T0 + timedelta(seconds=1)) is False
    assert token.token_hash == hash_token(raw)


def test_token_expires_after_ttl():
    token = RecoveryToken.issue("juan", raw_token="x", ttl_seconds=900, issued_at=T0)
    assert token.is_expired(now=T0 + timedelta(seconds=899)) is False
    assert token.is_expired(now=T0 + timedelta(seconds=901)) is True


def test_mark_used_sets_used_at():
    token = RecoveryToken.issue("juan", raw_token="x", issued_at=T0)
    used = token.mark_used(used_at=T0 + timedelta(seconds=5))
    assert used.is_used() is True
    assert used.used_at == T0 + timedelta(seconds=5)
    # original instance is unchanged (frozen dataclass)
    assert token.is_used() is False


def test_mark_used_twice_raises():
    token = RecoveryToken.issue("juan", raw_token="x", issued_at=T0)
    used = token.mark_used(used_at=T0)
    with pytest.raises(ValueError):
        used.mark_used(used_at=T0)


def test_invalidate_is_equivalent_to_mark_used():
    token = RecoveryToken.issue("juan", raw_token="x", issued_at=T0)
    invalidated = token.invalidate(at=T0 + timedelta(seconds=1))
    assert invalidated.is_used() is True


def test_issue_rejects_empty_user_reference():
    with pytest.raises(ValueError):
        RecoveryToken.issue("", raw_token="x")


def test_issue_rejects_non_positive_ttl():
    with pytest.raises(ValueError):
        RecoveryToken.issue("juan", raw_token="x", ttl_seconds=0)
