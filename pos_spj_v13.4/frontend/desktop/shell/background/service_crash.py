"""ServiceCrash — SHELL-14.

One recorded failure for one service — the history `RestartPolicy` (and
`AccountLockoutPolicy` before it, SHELL-1) operates over instead of a bare
counter, so decisions can depend on *when* failures happened, not just how
many.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ServiceCrash:
    service_id: str
    occurred_at: datetime
    error: BaseException
