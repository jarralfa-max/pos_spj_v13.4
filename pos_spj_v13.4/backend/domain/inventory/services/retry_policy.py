"""RetryPolicy — pure exponential backoff for outbox dispatch (§57, INV-22).

Decides how long to wait before the next dispatch attempt and when to give up
(dead-letter). No I/O, no clock: the caller supplies ``now`` and persists the
computed ``next_attempt_at``. Delays are integer seconds.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    base_seconds: int = 2
    factor: int = 2
    max_seconds: int = 3600
    max_attempts: int = 5

    def should_retry(self, attempts: int) -> bool:
        """True while the failed-attempt count is below the cap."""
        return attempts < self.max_attempts

    def next_delay_seconds(self, attempts: int) -> int:
        """Backoff after ``attempts`` failures (attempts>=1). Capped, deterministic."""
        if attempts < 1:
            attempts = 1
        delay = self.base_seconds * (self.factor ** (attempts - 1))
        return min(delay, self.max_seconds)
