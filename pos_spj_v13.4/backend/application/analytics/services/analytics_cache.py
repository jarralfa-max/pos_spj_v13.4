"""AnalyticsCache (§63) — the canonical cache-key shape for analytics reads.

`BiDashboardService` already has its own ad hoc TTL cache keyed by a filter
signature (kept as-is in BI-4 — it works and has test coverage). This module
is the **canonical** shape new BI-4+ consumers should use going forward: the
key must include company/scope/permissions/filters/metric-version/dataset-
version (§63), so two users with different permissions or different metric
definition versions never collide on the same cached entry — a stale or
over-permissioned cache hit would leak data across scopes, which is exactly
what §63 is guarding against.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from backend.domain.analytics.enums import ScopePolicy

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class AnalyticsCacheKey:
    company_id: str
    scope_policy: ScopePolicy
    scope_value: str
    permissions_hash: str
    filters_signature: str
    metric_version: int
    dataset_version: str

    def __post_init__(self) -> None:
        for field_name in ("company_id", "scope_value", "permissions_hash",
                           "filters_signature", "dataset_version"):
            if not getattr(self, field_name):
                raise ValueError(f"AnalyticsCacheKey.{field_name} is required")


class AnalyticsCache(Generic[T]):
    def __init__(self, ttl_seconds: int = 60, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._values: dict[AnalyticsCacheKey, T] = {}
        self._stored_at: dict[AnalyticsCacheKey, float] = {}

    def get(self, key: AnalyticsCacheKey) -> T | None:
        stored_at = self._stored_at.get(key)
        if stored_at is None:
            return None
        if self._clock() - stored_at > self._ttl:
            self._values.pop(key, None)
            self._stored_at.pop(key, None)
            return None
        return self._values.get(key)

    def set(self, key: AnalyticsCacheKey, value: T) -> None:
        self._values[key] = value
        self._stored_at[key] = self._clock()

    def invalidate(self, key: AnalyticsCacheKey | None = None) -> None:
        if key is None:
            self._values.clear()
            self._stored_at.clear()
            return
        self._values.pop(key, None)
        self._stored_at.pop(key, None)
