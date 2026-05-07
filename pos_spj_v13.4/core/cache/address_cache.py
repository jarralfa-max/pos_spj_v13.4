"""Thread-safe LRU cache with per-entry TTL for address autocomplete results.

Designed for concurrent QRunnable workers: all public methods are guarded by
a reentrant lock, so cache hits from the UI thread and cache writes from
worker threads are safe without additional synchronisation on the caller side.
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from threading import RLock
from typing import Any, Optional

logger = logging.getLogger("spj.cache.address")


class AddressCache:
    """LRU cache with TTL.

    Parameters
    ----------
    max_size:
        Maximum number of entries before LRU eviction kicks in.
    ttl:
        Time-to-live in seconds. Stale entries are lazily evicted on read.
    """

    def __init__(self, max_size: int = 200, ttl: int = 3600) -> None:
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._timestamps: dict[str, float] = {}
        self._max_size = max_size
        self._ttl = ttl
        self._lock = RLock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                logger.debug("cache MISS key=%r size=%d", key[:40], len(self._cache))
                return None
            if time.monotonic() - self._timestamps[key] > self._ttl:
                self._evict(key)
                self._misses += 1
                logger.debug("cache EXPIRED key=%r", key[:40])
                return None
            self._cache.move_to_end(key)
            self._hits += 1
            logger.debug("cache HIT key=%r", key[:40])
            return self._cache[key]

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            self._timestamps[key] = time.monotonic()
            self._enforce_limit()

    def invalidate(self, key: str) -> None:
        with self._lock:
            if key in self._cache:
                self._evict(key)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()

    @property
    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "size": len(self._cache),
                "max_size": self._max_size,
                "hit_rate_pct": round(hit_rate, 1),
            }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _evict(self, key: str) -> None:
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)
        self._evictions += 1

    def _enforce_limit(self) -> None:
        while len(self._cache) > self._max_size:
            oldest = next(iter(self._cache))
            self._evict(oldest)
            logger.debug("cache LRU evict key=%r", oldest[:40])
