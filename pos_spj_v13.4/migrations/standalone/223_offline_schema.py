# migrations/standalone/223_offline_schema.py
"""SET-23 — Offline schema (Cache, Version, Sync, Expiration).

Creates `offline_cache_entries`, `cache_expiration_policies` — a
born-clean, UUIDv7-native cache model scoped to a workstation
(`workstations`, SET-6), replacing the *concept* (not any live consumer)
of the two ad hoc caches already in this repo:
`backend/domain/settings/services/configuration_cache_service.py::
ConfigurationCache` (event-invalidated, no TTL) and legacy
`core/cache/address_cache.py::AddressCache` (hardcoded `ttl=3600`).

`sync/` (`SyncEngine`/`SyncWorker`/`ConflictResolver`, `migrations/
m000_base_schema.py`'s `sync_outbox`/`sync_inbox`/`sync_state`/
`sync_conflicts`/`sync_version_history` tables) is untouched — confirmed
dead infrastructure, never imported by `main.py`/`app_container`, per the
investigation already documented in
`docs/refactor/CRM-20_offline_sync_conflictos.md`.

DDL lives in backend/infrastructure/db/schema/offline_schema.py; only
this migration may call create_offline_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.offline_schema import create_offline_schema

logger = logging.getLogger("spj.migrations.223")


def run(conn) -> None:
    create_offline_schema(conn)
    conn.commit()
    logger.info("223: offline_cache_entries/cache_expiration_policies schema created.")


up = run
