"""Repository ports for the Offline bounded context — SET-23. Protocols
only — implementations land in
``backend/infrastructure/db/repositories/offline/``. Every id is a UUIDv7
string. Mirrors backend/domain/appearance/repository_ports.py.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.offline.entities.cache_expiration_policy import CacheExpirationPolicy
from backend.domain.offline.entities.offline_cache_entry import OfflineCacheEntry


class OfflineCacheEntryRepositoryPort(Protocol):
    def save(self, entry: OfflineCacheEntry) -> None: ...
    def get(self, entry_id: str) -> OfflineCacheEntry | None: ...
    def get_by_entity(
        self, *, entity_type: str, entity_id: str, workstation_id: str,
    ) -> OfflineCacheEntry | None: ...
    def list_for_workstation(self, workstation_id: str) -> list[OfflineCacheEntry]: ...


class CacheExpirationPolicyRepositoryPort(Protocol):
    def save(self, policy: CacheExpirationPolicy) -> None: ...
    def get(self, policy_id: str) -> CacheExpirationPolicy | None: ...
    def get_by_entity_type(self, entity_type: str) -> CacheExpirationPolicy | None: ...
    def list_active(self) -> list[CacheExpirationPolicy]: ...
