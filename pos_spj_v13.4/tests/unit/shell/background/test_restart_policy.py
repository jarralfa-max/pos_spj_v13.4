from datetime import datetime, timedelta, timezone

import pytest

from frontend.desktop.shell.background.restart_policy import RestartPolicy
from frontend.desktop.shell.background.service_crash import ServiceCrash

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _crash(at: datetime) -> ServiceCrash:
    return ServiceCrash(service_id="sync", occurred_at=at, error=RuntimeError("x"))


def test_no_crashes_gives_the_initial_backoff():
    policy = RestartPolicy(initial_backoff_seconds=1.0, backoff_multiplier=2.0, max_backoff_seconds=100)
    assert policy.next_restart_delay_seconds([], now=T0) == 1.0


def test_delay_grows_exponentially_with_crash_count_in_window():
    policy = RestartPolicy(
        max_restarts=10, window_seconds=3600, initial_backoff_seconds=1.0,
        backoff_multiplier=2.0, max_backoff_seconds=1000,
    )
    crashes = [_crash(T0), _crash(T0 + timedelta(seconds=1))]
    delay = policy.next_restart_delay_seconds(crashes, now=T0 + timedelta(seconds=2))
    assert delay == 1.0 * (2.0 ** 2)


def test_delay_is_capped_at_max_backoff_seconds():
    policy = RestartPolicy(
        max_restarts=100, window_seconds=3600, initial_backoff_seconds=1.0,
        backoff_multiplier=10.0, max_backoff_seconds=5.0,
    )
    crashes = [_crash(T0) for _ in range(5)]
    delay = policy.next_restart_delay_seconds(crashes, now=T0)
    assert delay == 5.0


def test_gives_up_once_max_restarts_reached_within_window():
    policy = RestartPolicy(max_restarts=3, window_seconds=3600)
    crashes = [_crash(T0), _crash(T0), _crash(T0)]
    assert policy.next_restart_delay_seconds(crashes, now=T0) is None
    assert policy.should_give_up(crashes, now=T0) is True


def test_crashes_outside_the_window_do_not_count():
    policy = RestartPolicy(max_restarts=2, window_seconds=60)
    old_crash = _crash(T0)
    now = T0 + timedelta(seconds=120)
    assert policy.should_give_up([old_crash], now=now) is False
    assert policy.next_restart_delay_seconds([old_crash], now=now) == policy.initial_backoff_seconds


def test_crashes_within_window_filters_correctly():
    policy = RestartPolicy(window_seconds=60)
    old_crash = _crash(T0)
    recent_crash = _crash(T0 + timedelta(seconds=50))
    now = T0 + timedelta(seconds=90)
    result = policy.crashes_within_window([old_crash, recent_crash], now=now)
    assert result == [recent_crash]


def test_a_streak_that_stops_and_resumes_later_starts_backoff_over():
    policy = RestartPolicy(max_restarts=3, window_seconds=60, initial_backoff_seconds=1.0, backoff_multiplier=2.0)
    old_streak = [_crash(T0), _crash(T0 + timedelta(seconds=1))]
    much_later = T0 + timedelta(hours=1)
    # both old crashes have fallen out of the window by "much_later"
    delay = policy.next_restart_delay_seconds(old_streak, now=much_later)
    assert delay == policy.initial_backoff_seconds


@pytest.mark.parametrize("field,value", [
    ("max_restarts", 0), ("window_seconds", -1), ("initial_backoff_seconds", -1),
    ("backoff_multiplier", 0.5),
])
def test_rejects_invalid_construction(field, value):
    kwargs = {field: value}
    with pytest.raises(ValueError):
        RestartPolicy(**kwargs)


def test_rejects_max_backoff_less_than_initial_backoff():
    with pytest.raises(ValueError):
        RestartPolicy(initial_backoff_seconds=10, max_backoff_seconds=5)
