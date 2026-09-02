from datetime import datetime, timedelta, timezone

import pytest

from backend.security.sessions.account_lockout_policy import AccountLockoutPolicy
from backend.security.sessions.authentication_attempt import AuthenticationAttempt
from backend.security.sessions.errors import AccountLockedError

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _failures(n: int, *, start=T0, step=timedelta(seconds=1)):
    return [
        AuthenticationAttempt.failure("juan", occurred_at=start + step * i)
        for i in range(n)
    ]


@pytest.fixture
def policy() -> AccountLockoutPolicy:
    return AccountLockoutPolicy(failed_attempt_limit=5, lockout_duration_seconds=900)


def test_not_locked_out_below_threshold(policy):
    attempts = _failures(4)
    assert policy.is_locked_out(attempts, now=T0 + timedelta(seconds=10)) is False


def test_locked_out_at_threshold(policy):
    attempts = _failures(5)
    now = attempts[-1].occurred_at + timedelta(seconds=1)
    assert policy.is_locked_out(attempts, now=now) is True


def test_unlocks_after_duration_elapses(policy):
    attempts = _failures(5)
    last_failure = attempts[-1].occurred_at
    still_locked = policy.is_locked_out(attempts, now=last_failure + timedelta(seconds=899))
    unlocked = policy.is_locked_out(attempts, now=last_failure + timedelta(seconds=901))
    assert still_locked is True
    assert unlocked is False


def test_successful_attempt_resets_the_streak(policy):
    attempts = _failures(4) + [
        AuthenticationAttempt.succeeded("juan", occurred_at=T0 + timedelta(seconds=10))
    ] + _failures(2, start=T0 + timedelta(seconds=20))
    # Only 2 consecutive failures after the success — below the limit of 5.
    now = T0 + timedelta(seconds=30)
    assert policy.is_locked_out(attempts, now=now) is False


def test_require_not_locked_out_raises_with_retry_after(policy):
    attempts = _failures(5)
    now = attempts[-1].occurred_at + timedelta(seconds=1)
    with pytest.raises(AccountLockedError) as exc:
        policy.require_not_locked_out(attempts, now=now)
    assert exc.value.retry_after_seconds == pytest.approx(899, abs=1)


def test_require_not_locked_out_silent_when_clear(policy):
    attempts = _failures(2)
    policy.require_not_locked_out(attempts, now=T0 + timedelta(seconds=5))  # no raise


def test_locked_until_returns_none_when_not_locked(policy):
    assert policy.locked_until(_failures(1), now=T0) is None


def test_locked_until_returns_unlock_moment(policy):
    attempts = _failures(5)
    unlock_at = policy.locked_until(attempts, now=attempts[-1].occurred_at)
    assert unlock_at == attempts[-1].occurred_at + timedelta(seconds=900)


def test_rejects_invalid_construction():
    with pytest.raises(ValueError):
        AccountLockoutPolicy(failed_attempt_limit=0)
    with pytest.raises(ValueError):
        AccountLockoutPolicy(lockout_duration_seconds=-1)


def test_empty_attempts_never_locked(policy):
    assert policy.is_locked_out([], now=T0) is False
