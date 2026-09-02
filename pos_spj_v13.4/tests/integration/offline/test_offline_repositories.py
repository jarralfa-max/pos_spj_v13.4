"""SET-23 — SqliteOfflineCacheEntryRepository +
SqliteCacheExpirationPolicyRepository against a real (in-memory) SQLite
born-clean schema (migration 223). `workstation_id` is a real FK into
Settings' `workstations` table (SET-6, migration 210).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.domain.offline.entities.cache_expiration_policy import CacheExpirationPolicy
from backend.domain.offline.entities.offline_cache_entry import OfflineCacheEntry
from backend.domain.offline.enums import CacheReadDecision, CacheSyncState
from backend.domain.offline.policies.offline_read_policy import resolve_cache_read
from backend.domain.settings.entities.workstation import Workstation
from backend.domain.settings.enums import WorkstationType
from backend.infrastructure.db.repositories.offline.cache_expiration_policy_repository import (
    SqliteCacheExpirationPolicyRepository,
)
from backend.infrastructure.db.repositories.offline.offline_cache_entry_repository import (
    SqliteOfflineCacheEntryRepository,
)
from backend.infrastructure.db.repositories.settings.workstation_repository import (
    SqliteWorkstationRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def cache_repo(conn):
    return SqliteOfflineCacheEntryRepository(conn)


@pytest.fixture
def policy_repo(conn):
    return SqliteCacheExpirationPolicyRepository(conn)


def _existing_branch_id(conn) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal de prueba"))
    return branch_id


@pytest.fixture
def workstation_id(conn):
    branch_id = _existing_branch_id(conn)
    workstation_repo = SqliteWorkstationRepository(conn)
    workstation = Workstation.create(
        branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type=WorkstationType.POS,
    )
    workstation_repo.save(workstation)
    conn.commit()
    return workstation.id


class TestOfflineCacheEntryRepository:
    def test_save_get_roundtrip(self, conn, cache_repo, workstation_id):
        entry = OfflineCacheEntry.create(
            entity_type="product", entity_id=new_uuid(), workstation_id=workstation_id,
            payload_json='{"name": "Coca-Cola 600ml"}', source_version="7",
        )
        cache_repo.save(entry)
        conn.commit()

        fetched = cache_repo.get(entry.id)
        assert fetched.source_version == "7"
        assert fetched.sync_state is CacheSyncState.FRESH

    def test_get_by_entity(self, conn, cache_repo, workstation_id):
        entity_id = new_uuid()
        entry = OfflineCacheEntry.create(
            entity_type="product", entity_id=entity_id, workstation_id=workstation_id,
            payload_json='{"name": "Coca-Cola 600ml"}', source_version="7",
        )
        cache_repo.save(entry)
        conn.commit()

        fetched = cache_repo.get_by_entity(
            entity_type="product", entity_id=entity_id, workstation_id=workstation_id,
        )
        assert fetched.id == entry.id

    def test_scope_uniqueness_blocks_duplicate_entry_for_same_workstation(self, conn, cache_repo, workstation_id):
        entity_id = new_uuid()
        first = OfflineCacheEntry.create(
            entity_type="product", entity_id=entity_id, workstation_id=workstation_id,
            payload_json='{"name": "A"}', source_version="1",
        )
        second = OfflineCacheEntry.create(
            entity_type="product", entity_id=entity_id, workstation_id=workstation_id,
            payload_json='{"name": "B"}', source_version="1",
        )
        cache_repo.save(first)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            cache_repo.save(second)
            conn.commit()
        conn.rollback()

    def test_refresh_and_persist_round_trip(self, conn, cache_repo, workstation_id):
        entry = OfflineCacheEntry.create(
            entity_type="product", entity_id=new_uuid(), workstation_id=workstation_id,
            payload_json='{"name": "A"}', source_version="1",
        )
        cache_repo.save(entry)
        conn.commit()

        entry.mark_stale()
        cache_repo.save(entry)
        conn.commit()
        assert cache_repo.get(entry.id).sync_state is CacheSyncState.STALE

        entry.refresh(source_version="2", payload_json='{"name": "B"}')
        cache_repo.save(entry)
        conn.commit()

        fetched = cache_repo.get(entry.id)
        assert fetched.sync_state is CacheSyncState.FRESH
        assert fetched.source_version == "2"

    def test_list_for_workstation(self, conn, cache_repo, workstation_id):
        first = OfflineCacheEntry.create(
            entity_type="product", entity_id=new_uuid(), workstation_id=workstation_id,
            payload_json='{"name": "A"}', source_version="1",
        )
        second = OfflineCacheEntry.create(
            entity_type="customer", entity_id=new_uuid(), workstation_id=workstation_id,
            payload_json='{"name": "B"}', source_version="1",
        )
        cache_repo.save(first)
        cache_repo.save(second)
        conn.commit()

        entries = cache_repo.list_for_workstation(workstation_id)
        assert {e.id for e in entries} == {first.id, second.id}


class TestCacheExpirationPolicyRepository:
    def test_save_get_roundtrip(self, conn, policy_repo):
        policy = CacheExpirationPolicy.create(entity_type="product", ttl_seconds=3600)
        policy_repo.save(policy)
        conn.commit()

        fetched = policy_repo.get(policy.id)
        assert fetched.ttl_seconds == 3600

    def test_get_by_entity_type(self, conn, policy_repo):
        policy = CacheExpirationPolicy.create(entity_type="product", ttl_seconds=3600)
        policy_repo.save(policy)
        conn.commit()
        assert policy_repo.get_by_entity_type("product").id == policy.id

    def test_entity_type_is_unique(self, conn, policy_repo):
        policy_repo.save(CacheExpirationPolicy.create(entity_type="product", ttl_seconds=3600))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            policy_repo.save(CacheExpirationPolicy.create(entity_type="product", ttl_seconds=7200))
            conn.commit()
        conn.rollback()

    def test_list_active_excludes_inactive(self, conn, policy_repo):
        active = CacheExpirationPolicy.create(entity_type="product", ttl_seconds=3600)
        inactive = CacheExpirationPolicy.create(entity_type="customer", ttl_seconds=3600)
        inactive.deactivate()
        policy_repo.save(active)
        policy_repo.save(inactive)
        conn.commit()

        entity_types = {p.entity_type for p in policy_repo.list_active()}
        assert entity_types == {"product"}


class TestComposesWithOfflineReadPolicyEndToEnd:
    def test_online_stale_entry_requires_refresh(self, conn, cache_repo, policy_repo, workstation_id):
        entity_id = new_uuid()
        entry = OfflineCacheEntry.create(
            entity_type="product", entity_id=entity_id, workstation_id=workstation_id,
            payload_json='{"name": "A"}', source_version="1",
        )
        policy = CacheExpirationPolicy.create(entity_type="product", ttl_seconds=3600)
        cache_repo.save(entry)
        policy_repo.save(policy)
        conn.commit()

        fetched_entry = cache_repo.get_by_entity(
            entity_type="product", entity_id=entity_id, workstation_id=workstation_id,
        )
        fetched_policy = policy_repo.get_by_entity_type("product")
        now = datetime.fromisoformat(fetched_entry.cached_at) + timedelta(seconds=10)

        decision = resolve_cache_read(
            fetched_entry, ttl_seconds=fetched_policy.ttl_seconds, now=now, is_online=True,
            origin_version="2",
        )
        assert decision is CacheReadDecision.REFRESH_REQUIRED

    def test_offline_stale_entry_still_serves_best_effort_cache(self, conn, cache_repo, policy_repo, workstation_id):
        entity_id = new_uuid()
        entry = OfflineCacheEntry.create(
            entity_type="product", entity_id=entity_id, workstation_id=workstation_id,
            payload_json='{"name": "A"}', source_version="1",
        )
        policy = CacheExpirationPolicy.create(entity_type="product", ttl_seconds=3600)
        cache_repo.save(entry)
        policy_repo.save(policy)
        conn.commit()

        fetched_entry = cache_repo.get_by_entity(
            entity_type="product", entity_id=entity_id, workstation_id=workstation_id,
        )
        fetched_policy = policy_repo.get_by_entity_type("product")
        now = datetime.fromisoformat(fetched_entry.cached_at) + timedelta(seconds=10)

        decision = resolve_cache_read(
            fetched_entry, ttl_seconds=fetched_policy.ttl_seconds, now=now, is_online=False,
            origin_version="2",
        )
        assert decision is CacheReadDecision.USE_CACHE_STALE_OFFLINE
