"""CacheExpirationEvaluationPolicy — SET-23 "Expiration": has an
`OfflineCacheEntry` outlived its TTL? Pure wall-clock comparison against
`entry.cached_at` — `ttl_seconds` is always supplied by the caller (from
a `CacheExpirationPolicy` looked up by `entity_type`), never guessed here.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.domain.offline.entities.offline_cache_entry import OfflineCacheEntry


def is_expired(entry: OfflineCacheEntry, *, ttl_seconds: int, now: datetime) -> bool:
    cached_at = datetime.fromisoformat(entry.cached_at)
    return (now - cached_at) > timedelta(seconds=ttl_seconds)
