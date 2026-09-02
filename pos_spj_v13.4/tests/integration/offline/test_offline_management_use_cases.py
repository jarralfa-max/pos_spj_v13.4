"""SET-23 repegado — CreateCacheExpirationPolicyUseCase/
UpdateCacheExpirationPolicyUseCase/ChangeCacheExpirationPolicyStatusUseCase
against a real (in-memory) SQLite born-clean schema (migration 223).
Closes the origination gap: before this round nothing called
`CacheExpirationPolicy.create()` outside of tests. `OfflineCacheEntry`
deliberately has no use cases — it's a runtime artifact with no real
consumer yet (see `offline_management_use_cases.py`'s module docstring).
"""

from __future__ import annotations

import pytest

from backend.domain.offline.exceptions import (
    CacheExpirationPolicyEntityTypeOccupiedError,
    CacheExpirationPolicyNotFoundError,
)
from backend.application.use_cases.configuracion.offline_management_use_cases import (
    CacheExpirationPolicyStatusAction,
    ChangeCacheExpirationPolicyStatusUseCase,
    CreateCacheExpirationPolicyUseCase,
    UpdateCacheExpirationPolicyUseCase,
)
from backend.infrastructure.db.repositories.offline.cache_expiration_policy_repository import (
    SqliteCacheExpirationPolicyRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


class TestCreateCacheExpirationPolicyUseCase:
    def test_creates_and_persists(self, conn):
        policy = CreateCacheExpirationPolicyUseCase(conn).execute(entity_type="customer", ttl_seconds=3600)
        assert SqliteCacheExpirationPolicyRepository(conn).get(policy.id) is not None

    def test_rejects_duplicate_entity_type(self, conn):
        uc = CreateCacheExpirationPolicyUseCase(conn)
        uc.execute(entity_type="customer", ttl_seconds=3600)
        with pytest.raises(CacheExpirationPolicyEntityTypeOccupiedError):
            uc.execute(entity_type="customer", ttl_seconds=7200)


class TestUpdateCacheExpirationPolicyUseCase:
    def test_updates_ttl(self, conn):
        policy = CreateCacheExpirationPolicyUseCase(conn).execute(entity_type="product", ttl_seconds=3600)
        updated = UpdateCacheExpirationPolicyUseCase(conn).execute(policy_id=policy.id, ttl_seconds=7200)
        assert updated.ttl_seconds == 7200

    def test_raises_when_missing(self, conn):
        with pytest.raises(CacheExpirationPolicyNotFoundError):
            UpdateCacheExpirationPolicyUseCase(conn).execute(policy_id=new_uuid(), ttl_seconds=7200)


class TestChangeCacheExpirationPolicyStatusUseCase:
    def test_deactivate_then_activate(self, conn):
        policy = CreateCacheExpirationPolicyUseCase(conn).execute(entity_type="branch", ttl_seconds=1800)
        uc = ChangeCacheExpirationPolicyStatusUseCase(conn)
        deactivated = uc.execute(policy_id=policy.id, action=CacheExpirationPolicyStatusAction.DEACTIVATE)
        assert deactivated.active is False
        activated = uc.execute(policy_id=policy.id, action=CacheExpirationPolicyStatusAction.ACTIVATE)
        assert activated.active is True

    def test_raises_when_missing(self, conn):
        with pytest.raises(CacheExpirationPolicyNotFoundError):
            ChangeCacheExpirationPolicyStatusUseCase(conn).execute(
                policy_id=new_uuid(), action=CacheExpirationPolicyStatusAction.ACTIVATE)
