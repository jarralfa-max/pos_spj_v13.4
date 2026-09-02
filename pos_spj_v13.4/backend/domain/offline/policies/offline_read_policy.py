"""OfflineReadPolicy — SET-23: ties "Cache"/"Version"/"Sync"/"Expiration"
together into the one decision an offline-first read path actually needs:
what should the caller do with this cached entry right now?

`is_online` is a plain boolean the caller computes (typically via
`backend.domain.settings.entities.workstation.Workstation.is_online()`),
never recomputed here — mirrors that entity's own discipline of never
guessing its own staleness threshold, and keeps this bounded context
independent of `settings` (no cross-context import, same independence
every prior SET in this track already established).

The genuinely "offline-first" behavior: when offline, a stale or expired
cache is still the best available answer (`USE_CACHE_STALE_OFFLINE`) —
never `NO_CACHE_AVAILABLE` just because the clock or version moved on.
When online, staleness or expiration means a real refresh is possible, so
it's requested instead of silently served.
"""

from __future__ import annotations

from datetime import datetime

from backend.domain.offline.entities.offline_cache_entry import OfflineCacheEntry
from backend.domain.offline.enums import CacheReadDecision, CacheSyncState
from backend.domain.offline.policies.cache_expiration_evaluation_policy import is_expired
from backend.domain.offline.policies.cache_version_sync_policy import evaluate_sync_state


def resolve_cache_read(
    entry: OfflineCacheEntry | None, *, ttl_seconds: int, now: datetime, is_online: bool,
    origin_version: str | None = None,
) -> CacheReadDecision:
    if entry is None:
        return CacheReadDecision.NO_CACHE_AVAILABLE

    expired = is_expired(entry, ttl_seconds=ttl_seconds, now=now)
    stale = origin_version is not None and evaluate_sync_state(entry, origin_version) is CacheSyncState.STALE
    needs_refresh = expired or stale

    if not is_online:
        return CacheReadDecision.USE_CACHE_STALE_OFFLINE if needs_refresh else CacheReadDecision.USE_CACHE_FRESH

    return CacheReadDecision.REFRESH_REQUIRED if needs_refresh else CacheReadDecision.USE_CACHE_FRESH
