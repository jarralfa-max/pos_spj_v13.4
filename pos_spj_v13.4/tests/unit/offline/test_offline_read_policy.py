"""SET-23 — "Sync"/"Expiration": cache_expiration_evaluation_policy.
is_expired, cache_version_sync_policy.evaluate_sync_state, and the
composing offline_read_policy.resolve_cache_read. Pure domain — no DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.domain.offline.entities.offline_cache_entry import OfflineCacheEntry
from backend.domain.offline.enums import CacheReadDecision, CacheSyncState
from backend.domain.offline.policies.cache_expiration_evaluation_policy import is_expired
from backend.domain.offline.policies.cache_version_sync_policy import evaluate_sync_state
from backend.domain.offline.policies.offline_read_policy import resolve_cache_read
from backend.shared.ids import new_uuid


def _entry(**overrides) -> OfflineCacheEntry:
    kwargs = dict(
        entity_type="product", entity_id=new_uuid(), workstation_id=new_uuid(),
        payload_json='{"name": "Coca-Cola 600ml"}', source_version="7",
    )
    kwargs.update(overrides)
    return OfflineCacheEntry.create(**kwargs)


class TestIsExpired:
    def test_within_ttl_is_not_expired(self):
        entry = _entry()
        now = datetime.fromisoformat(entry.cached_at) + timedelta(seconds=10)
        assert is_expired(entry, ttl_seconds=3600, now=now) is False

    def test_beyond_ttl_is_expired(self):
        entry = _entry()
        now = datetime.fromisoformat(entry.cached_at) + timedelta(seconds=3601)
        assert is_expired(entry, ttl_seconds=3600, now=now) is True

    def test_exactly_at_ttl_boundary_is_not_expired(self):
        entry = _entry()
        now = datetime.fromisoformat(entry.cached_at) + timedelta(seconds=3600)
        assert is_expired(entry, ttl_seconds=3600, now=now) is False


class TestEvaluateSyncState:
    def test_matching_version_is_fresh(self):
        entry = _entry(source_version="7")
        assert evaluate_sync_state(entry, "7") is CacheSyncState.FRESH

    def test_different_version_is_stale(self):
        entry = _entry(source_version="7")
        assert evaluate_sync_state(entry, "8") is CacheSyncState.STALE


class TestResolveCacheRead:
    def test_no_entry_returns_no_cache_available(self):
        now = datetime.now(timezone.utc)
        assert resolve_cache_read(None, ttl_seconds=3600, now=now, is_online=True) is (
            CacheReadDecision.NO_CACHE_AVAILABLE
        )

    def test_fresh_within_ttl_online_uses_cache(self):
        entry = _entry(source_version="7")
        now = datetime.fromisoformat(entry.cached_at) + timedelta(seconds=10)
        decision = resolve_cache_read(
            entry, ttl_seconds=3600, now=now, is_online=True, origin_version="7",
        )
        assert decision is CacheReadDecision.USE_CACHE_FRESH

    def test_expired_online_requires_refresh(self):
        entry = _entry(source_version="7")
        now = datetime.fromisoformat(entry.cached_at) + timedelta(seconds=3601)
        decision = resolve_cache_read(entry, ttl_seconds=3600, now=now, is_online=True)
        assert decision is CacheReadDecision.REFRESH_REQUIRED

    def test_stale_version_online_requires_refresh(self):
        entry = _entry(source_version="7")
        now = datetime.fromisoformat(entry.cached_at) + timedelta(seconds=10)
        decision = resolve_cache_read(
            entry, ttl_seconds=3600, now=now, is_online=True, origin_version="8",
        )
        assert decision is CacheReadDecision.REFRESH_REQUIRED

    def test_expired_offline_still_uses_cache_as_best_effort(self):
        entry = _entry(source_version="7")
        now = datetime.fromisoformat(entry.cached_at) + timedelta(seconds=3601)
        decision = resolve_cache_read(entry, ttl_seconds=3600, now=now, is_online=False)
        assert decision is CacheReadDecision.USE_CACHE_STALE_OFFLINE

    def test_stale_version_offline_still_uses_cache_as_best_effort(self):
        entry = _entry(source_version="7")
        now = datetime.fromisoformat(entry.cached_at) + timedelta(seconds=10)
        decision = resolve_cache_read(
            entry, ttl_seconds=3600, now=now, is_online=False, origin_version="8",
        )
        assert decision is CacheReadDecision.USE_CACHE_STALE_OFFLINE

    def test_fresh_offline_uses_cache_fresh_not_stale_variant(self):
        entry = _entry(source_version="7")
        now = datetime.fromisoformat(entry.cached_at) + timedelta(seconds=10)
        decision = resolve_cache_read(
            entry, ttl_seconds=3600, now=now, is_online=False, origin_version="7",
        )
        assert decision is CacheReadDecision.USE_CACHE_FRESH

    def test_no_origin_version_supplied_only_expiration_drives_staleness(self):
        entry = _entry(source_version="7")
        now = datetime.fromisoformat(entry.cached_at) + timedelta(seconds=10)
        decision = resolve_cache_read(entry, ttl_seconds=3600, now=now, is_online=True)
        assert decision is CacheReadDecision.USE_CACHE_FRESH
