"""OfflineCacheEntry — SET-23 "Cache"/"Version": one locally-cached
snapshot of a remote/shared entity, scoped to the workstation that cached
it. Generalizes the two ad hoc cache patterns already in this repo —
`backend/domain/settings/services/configuration_cache_service.py::
ConfigurationCache` (event-invalidated, no TTL) and the legacy
`core/cache/address_cache.py::AddressCache` (TTL+LRU, hardcoded
`ttl=3600`) — into one typed, persisted model that also carries
`source_version`, so staleness can be detected by comparing versions
(§"Sync"), not just by wall-clock age (§"Expiration").

`source_version` is a free-form string deliberately: it mirrors whatever
version marker the origin entity already carries (an integer `version`
column, an `updated_at` timestamp, a content hash — same "reuse what
already exists" discipline `docs/refactor/CRM-20_offline_sync_conflictos.md`
established for optimistic concurrency), not a new versioning scheme this
bounded context invents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.offline.enums import CacheSyncState
from backend.domain.offline.exceptions import OfflineInvalidValueError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class OfflineCacheEntry:
    id: str
    entity_type: str
    entity_id: str
    workstation_id: str
    payload_json: str
    source_version: str
    sync_state: CacheSyncState = CacheSyncState.FRESH
    cached_at: str = field(default_factory=_utcnow)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, entity_type: str, entity_id: str, workstation_id: str, payload_json: str,
        source_version: str,
    ) -> "OfflineCacheEntry":
        if not entity_type.strip():
            raise OfflineInvalidValueError("entity_type es obligatorio")
        if not entity_id.strip():
            raise OfflineInvalidValueError("entity_id es obligatorio")
        if not payload_json.strip():
            raise OfflineInvalidValueError("payload_json es obligatorio")
        if not source_version.strip():
            raise OfflineInvalidValueError("source_version es obligatorio")
        cached_at = _utcnow()
        return cls(
            id=new_uuid(), entity_type=entity_type.strip(), entity_id=entity_id.strip(),
            workstation_id=validate_uuidv7(workstation_id), payload_json=payload_json,
            source_version=source_version.strip(), cached_at=cached_at,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def refresh(self, *, source_version: str, payload_json: str) -> None:
        if not source_version.strip():
            raise OfflineInvalidValueError("source_version es obligatorio")
        if not payload_json.strip():
            raise OfflineInvalidValueError("payload_json es obligatorio")
        self.source_version = source_version.strip()
        self.payload_json = payload_json
        self.sync_state = CacheSyncState.FRESH
        self.cached_at = _utcnow()
        self._touch()

    def mark_stale(self) -> None:
        self.sync_state = CacheSyncState.STALE
        self._touch()
