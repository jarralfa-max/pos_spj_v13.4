"""RestartPolicy — SHELL-14.

Pure decision logic for automatic restarts after a crash, same shape as
SHELL-1's `AccountLockoutPolicy`: given the recent `ServiceCrash` history
for a service, decide what happens next. No storage, no scheduling side
effects, no clock reads except through an injectable `now` — the caller
(`BackgroundServiceSupervisor`) owns persistence and actually invoking the
delay.

Exponential backoff (`initial_backoff_seconds * backoff_multiplier ** N`,
capped at `max_backoff_seconds`) where `N` is how many crashes already
happened *within the rolling window* — not how many ever happened, so a
service that crashed twice, ran fine for a day, then crashed again starts
its backoff over rather than picking up where a long-past streak left off.
Once `max_restarts` crashes land inside that same window,
`next_restart_delay_seconds()` returns `None` — "give up," not "wait
forever" — and the supervisor marks the service `FAILED` rather than
retrying indefinitely.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from frontend.desktop.shell.background.service_crash import ServiceCrash


class RestartPolicy:
    def __init__(
        self, *,
        max_restarts: int = 5,
        window_seconds: int = 300,
        initial_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 60.0,
        backoff_multiplier: float = 2.0,
    ) -> None:
        if max_restarts < 1:
            raise ValueError("max_restarts debe ser >= 1.")
        if window_seconds < 0:
            raise ValueError("window_seconds no puede ser negativo.")
        if initial_backoff_seconds < 0:
            raise ValueError("initial_backoff_seconds no puede ser negativo.")
        if max_backoff_seconds < initial_backoff_seconds:
            raise ValueError("max_backoff_seconds no puede ser menor que initial_backoff_seconds.")
        if backoff_multiplier < 1:
            raise ValueError("backoff_multiplier debe ser >= 1.")
        self.max_restarts = max_restarts
        self.window_seconds = window_seconds
        self.initial_backoff_seconds = initial_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.backoff_multiplier = backoff_multiplier

    def crashes_within_window(
        self, crashes: list[ServiceCrash], *, now: datetime | None = None,
    ) -> list[ServiceCrash]:
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.window_seconds)
        return [c for c in crashes if c.occurred_at >= cutoff]

    def should_give_up(self, crashes: list[ServiceCrash], *, now: datetime | None = None) -> bool:
        return len(self.crashes_within_window(crashes, now=now)) >= self.max_restarts

    def next_restart_delay_seconds(
        self, crashes: list[ServiceCrash], *, now: datetime | None = None,
    ) -> float | None:
        now = now or datetime.now(timezone.utc)
        recent = self.crashes_within_window(crashes, now=now)
        if len(recent) >= self.max_restarts:
            return None
        delay = self.initial_backoff_seconds * (self.backoff_multiplier ** len(recent))
        return min(delay, self.max_backoff_seconds)


DEFAULT_RESTART_POLICY = RestartPolicy()
