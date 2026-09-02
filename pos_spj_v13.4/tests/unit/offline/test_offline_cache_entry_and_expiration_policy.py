"""SET-23 — "Cache"/"Version"/"Expiration": OfflineCacheEntry +
CacheExpirationPolicy entities. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.offline.entities.cache_expiration_policy import CacheExpirationPolicy
from backend.domain.offline.entities.offline_cache_entry import OfflineCacheEntry
from backend.domain.offline.enums import CacheSyncState
from backend.domain.offline.exceptions import OfflineInvalidValueError
from backend.shared.ids import is_uuidv7, new_uuid


def _entry(**overrides) -> OfflineCacheEntry:
    kwargs = dict(
        entity_type="product", entity_id=new_uuid(), workstation_id=new_uuid(),
        payload_json='{"name": "Coca-Cola 600ml"}', source_version="7",
    )
    kwargs.update(overrides)
    return OfflineCacheEntry.create(**kwargs)


class TestOfflineCacheEntryCreate:
    def test_mints_uuidv7_and_defaults(self):
        entry = _entry()
        assert is_uuidv7(entry.id)
        assert entry.sync_state is CacheSyncState.FRESH
        assert entry.cached_at

    def test_requires_entity_type(self):
        with pytest.raises(OfflineInvalidValueError):
            _entry(entity_type="   ")

    def test_requires_entity_id(self):
        with pytest.raises(OfflineInvalidValueError):
            _entry(entity_id="   ")

    def test_requires_payload_json(self):
        with pytest.raises(OfflineInvalidValueError):
            _entry(payload_json="   ")

    def test_requires_source_version(self):
        with pytest.raises(OfflineInvalidValueError):
            _entry(source_version="   ")

    def test_validates_workstation_id_as_uuidv7(self):
        with pytest.raises(Exception):
            _entry(workstation_id="not-a-uuid")


class TestOfflineCacheEntryRefreshAndStale:
    def test_refresh_updates_version_payload_and_resets_to_fresh(self):
        entry = _entry(source_version="7")
        entry.mark_stale()
        assert entry.sync_state is CacheSyncState.STALE

        entry.refresh(source_version="8", payload_json='{"name": "Coca-Cola 600ml", "price": "18.50"}')
        assert entry.source_version == "8"
        assert entry.sync_state is CacheSyncState.FRESH
        assert "18.50" in entry.payload_json

    def test_refresh_rejects_blank_version(self):
        entry = _entry()
        with pytest.raises(OfflineInvalidValueError):
            entry.refresh(source_version="   ", payload_json="{}")

    def test_refresh_rejects_blank_payload(self):
        entry = _entry()
        with pytest.raises(OfflineInvalidValueError):
            entry.refresh(source_version="9", payload_json="   ")

    def test_mark_stale_does_not_touch_cached_at(self):
        entry = _entry()
        cached_at_before = entry.cached_at
        entry.mark_stale()
        assert entry.cached_at == cached_at_before


def _policy(**overrides) -> CacheExpirationPolicy:
    kwargs = dict(entity_type="product", ttl_seconds=3600)
    kwargs.update(overrides)
    return CacheExpirationPolicy.create(**kwargs)


class TestCacheExpirationPolicyCreate:
    def test_mints_uuidv7_and_defaults(self):
        policy = _policy()
        assert is_uuidv7(policy.id)
        assert policy.active is True

    def test_requires_entity_type(self):
        with pytest.raises(OfflineInvalidValueError):
            _policy(entity_type="   ")

    @pytest.mark.parametrize("ttl_seconds", [0, -60, 1.5, True])
    def test_rejects_invalid_ttl(self, ttl_seconds):
        with pytest.raises(OfflineInvalidValueError):
            _policy(ttl_seconds=ttl_seconds)

    def test_activate_deactivate(self):
        policy = _policy()
        policy.deactivate()
        assert policy.active is False
        policy.activate()
        assert policy.active is True

    def test_change_ttl(self):
        policy = _policy()
        policy.change_ttl(7200)
        assert policy.ttl_seconds == 7200

    def test_change_ttl_rejects_zero(self):
        policy = _policy()
        with pytest.raises(OfflineInvalidValueError):
            policy.change_ttl(0)
