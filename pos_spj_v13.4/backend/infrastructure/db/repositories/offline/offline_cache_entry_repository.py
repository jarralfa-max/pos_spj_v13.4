"""SqliteOfflineCacheEntryRepository — persists `OfflineCacheEntry`
(SET-23). Implements
`backend.domain.offline.repository_ports.OfflineCacheEntryRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.offline.entities.offline_cache_entry import OfflineCacheEntry
from backend.domain.offline.enums import CacheSyncState
from backend.infrastructure.db.repositories.offline.base import OfflineRepositoryBase

_COLS = (
    "id, entity_type, entity_id, workstation_id, payload_json, source_version, sync_state, cached_at,"
    " created_at, updated_at"
)


class SqliteOfflineCacheEntryRepository(OfflineRepositoryBase):
    def save(self, entry: OfflineCacheEntry) -> None:
        self._execute(
            f"INSERT INTO offline_cache_entries ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " payload_json=excluded.payload_json, source_version=excluded.source_version,"
            " sync_state=excluded.sync_state, cached_at=excluded.cached_at,"
            " updated_at=excluded.updated_at",
            self._params(entry),
        )

    def get(self, entry_id: str) -> OfflineCacheEntry | None:
        row = self._query_one(f"SELECT {_COLS} FROM offline_cache_entries WHERE id=?", (entry_id,))
        return self._hydrate(row) if row else None

    def get_by_entity(
        self, *, entity_type: str, entity_id: str, workstation_id: str,
    ) -> OfflineCacheEntry | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM offline_cache_entries"
            " WHERE entity_type=? AND entity_id=? AND workstation_id=?",
            (entity_type.strip(), entity_id.strip(), workstation_id),
        )
        return self._hydrate(row) if row else None

    def list_for_workstation(self, workstation_id: str) -> list[OfflineCacheEntry]:
        rows = self._query(
            f"SELECT {_COLS} FROM offline_cache_entries WHERE workstation_id=? ORDER BY entity_type,"
            " entity_id",
            (workstation_id,),
        )
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[OfflineCacheEntry]:
        rows = self._query(f"SELECT {_COLS} FROM offline_cache_entries ORDER BY entity_type, entity_id")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(entry: OfflineCacheEntry) -> tuple:
        return (
            entry.id, entry.entity_type, entry.entity_id, entry.workstation_id, entry.payload_json,
            entry.source_version, entry.sync_state.value, entry.cached_at, entry.created_at,
            entry.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> OfflineCacheEntry:
        return OfflineCacheEntry(
            id=row["id"], entity_type=row["entity_type"], entity_id=row["entity_id"],
            workstation_id=row["workstation_id"], payload_json=row["payload_json"],
            source_version=row["source_version"], sync_state=CacheSyncState(row["sync_state"]),
            cached_at=row["cached_at"], created_at=row["created_at"], updated_at=row["updated_at"],
        )
