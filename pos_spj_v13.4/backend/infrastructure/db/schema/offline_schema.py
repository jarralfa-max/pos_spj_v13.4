"""Offline schema — SET-23.

DDL lives only here; only migration 223 may call `create_offline_schema`.
Backs `backend/domain/offline/` (SET-23): `offline_cache_entries` mirrors
`OfflineCacheEntry`, `cache_expiration_policies` mirrors
`CacheExpirationPolicy`.

No legacy table-name collision — the legacy `sync_*` tables
(`sync_outbox`/`sync_inbox`/`sync_state`/`sync_conflicts`/
`sync_version_history`, `migrations/m000_base_schema.py`) back a
different concept (an outbox/inbox replication engine, confirmed dead —
`sync/SyncEngine` is never imported by `main.py`) and are untouched by
this schema. `workstation_id` is a real FK into Settings'
`workstations` table (SET-6) — a cache entry always belongs to the
workstation that cached it.
"""

from __future__ import annotations

_UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"


def _uuid(column: str) -> str:
    return _UUID_CHECK.format(column)


_SYNC_STATES = "'FRESH','STALE'"

_OFFLINE_CACHE_ENTRIES_DDL = f"""
    CREATE TABLE IF NOT EXISTS offline_cache_entries (
        id                TEXT PRIMARY KEY CHECK({_uuid('id')}),
        entity_type       TEXT NOT NULL CHECK(trim(entity_type)<>''),
        entity_id         TEXT NOT NULL CHECK(trim(entity_id)<>''),
        workstation_id    TEXT NOT NULL REFERENCES workstations(id) CHECK({_uuid('workstation_id')}),
        payload_json      TEXT NOT NULL CHECK(trim(payload_json)<>''),
        source_version    TEXT NOT NULL CHECK(trim(source_version)<>''),
        sync_state        TEXT NOT NULL CHECK(sync_state IN ({_SYNC_STATES})),
        cached_at         TEXT NOT NULL,
        created_at        TEXT NOT NULL,
        updated_at        TEXT NOT NULL
    )
"""

_CACHE_EXPIRATION_POLICIES_DDL = f"""
    CREATE TABLE IF NOT EXISTS cache_expiration_policies (
        id            TEXT PRIMARY KEY CHECK({_uuid('id')}),
        entity_type   TEXT NOT NULL UNIQUE CHECK(trim(entity_type)<>''),
        ttl_seconds   INTEGER NOT NULL CHECK(ttl_seconds > 0),
        active        INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    )
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_offline_cache_entries_workstation "
    "ON offline_cache_entries(workstation_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_offline_cache_entries_scope "
    "ON offline_cache_entries(entity_type, entity_id, workstation_id)",
    "CREATE INDEX IF NOT EXISTS idx_cache_expiration_policies_active ON cache_expiration_policies(active)",
)


def create_offline_schema(conn) -> None:
    conn.execute(_OFFLINE_CACHE_ENTRIES_DDL)
    conn.execute(_CACHE_EXPIRATION_POLICIES_DDL)
    for statement in _INDEXES:
        conn.execute(statement)
