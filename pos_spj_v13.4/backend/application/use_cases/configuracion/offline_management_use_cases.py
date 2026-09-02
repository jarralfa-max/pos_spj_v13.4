"""Use cases for the "Offline" section — CRUD for the "Expiration" pillar
(`CacheExpirationPolicy`) only. Same thin-orchestration shape as
`feature_flag_management_use_cases.py`/`appearance_management_use_cases.py`.

Deliberately NO use cases for `OfflineCacheEntry` ("Cache"/"Version"/
"Sync") — it is a runtime artifact meant to be written by a real
offline-first read consumer, and no such consumer exists in this repo
(`sync/` is confirmed dead, never imported by `main.py`). Hand-authoring
a cache entry via an admin form doesn't reflect any real workflow, same
restraint `backend/domain/offline/enums.py` already documents for not
fabricating a `sync_status` pipeline without a real producer.
"""

from __future__ import annotations

from enum import Enum

from backend.domain.offline.entities.cache_expiration_policy import CacheExpirationPolicy
from backend.domain.offline.exceptions import (
    CacheExpirationPolicyEntityTypeOccupiedError,
    CacheExpirationPolicyNotFoundError,
)
from backend.infrastructure.db.repositories.offline.cache_expiration_policy_repository import (
    SqliteCacheExpirationPolicyRepository,
)


class CacheExpirationPolicyStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


class CreateCacheExpirationPolicyUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._policies = SqliteCacheExpirationPolicyRepository(connection)

    def execute(self, *, entity_type: str, ttl_seconds: int) -> CacheExpirationPolicy:
        if self._policies.get_by_entity_type(entity_type) is not None:
            raise CacheExpirationPolicyEntityTypeOccupiedError(
                f"Ya existe una política de expiración para {entity_type!r}"
            )
        policy = CacheExpirationPolicy.create(entity_type=entity_type, ttl_seconds=ttl_seconds)
        self._policies.save(policy)
        self._conn.commit()
        return policy


class UpdateCacheExpirationPolicyUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._policies = SqliteCacheExpirationPolicyRepository(connection)

    def execute(self, *, policy_id: str, ttl_seconds: int) -> CacheExpirationPolicy:
        policy = self._policies.get(policy_id)
        if policy is None:
            raise CacheExpirationPolicyNotFoundError(f"Política de expiración {policy_id} no encontrada")
        policy.change_ttl(ttl_seconds)
        self._policies.save(policy)
        self._conn.commit()
        return policy


class ChangeCacheExpirationPolicyStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._policies = SqliteCacheExpirationPolicyRepository(connection)

    def execute(self, *, policy_id: str, action: CacheExpirationPolicyStatusAction) -> CacheExpirationPolicy:
        policy = self._policies.get(policy_id)
        if policy is None:
            raise CacheExpirationPolicyNotFoundError(f"Política de expiración {policy_id} no encontrada")

        if action is CacheExpirationPolicyStatusAction.ACTIVATE:
            policy.activate()
        elif action is CacheExpirationPolicyStatusAction.DEACTIVATE:
            policy.deactivate()

        self._policies.save(policy)
        self._conn.commit()
        return policy
