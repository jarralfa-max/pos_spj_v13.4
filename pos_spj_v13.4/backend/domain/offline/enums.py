"""Canonical enums for the Offline bounded context — SET-23.

Legacy inventory: `sync/` (`SyncEngine`/`SyncWorker`/`ConflictResolver`,
Lamport-clock outbox/inbox) is a complete engine but hardcoded to a fixed
legacy table list and **never imported by `main.py`/`app_container`** —
confirmed dead infrastructure, already independently documented in
`docs/refactor/CRM-20_offline_sync_conflictos.md` §"Investigación previa",
which explicitly declined to extend it for the same reason this SET does.
That same document found this repo runs today on a single shared SQLite
file with no real central server or multi-terminal transport — so this
bounded context does NOT invent a `sync_status` pipeline
(`LOCAL_PENDING`/`SYNCING`/...) with no real producer, the same restraint
CRM-20 already exercised. `CacheSyncState` stays a deliberately minimal
two-value comparison (does the cache reflect the same version as the
origin, yes or no), not a fabricated multi-stage lifecycle.
"""

from __future__ import annotations

from enum import Enum


class CacheSyncState(str, Enum):
    """"Sync": whether an `OfflineCacheEntry` reflects the same
    `source_version` the origin last reported. Generalizes the version/
    `updated_at` comparison
    `DetectCustomerSyncConflictUseCase`/`DetectCRMSyncConflictUseCase`
    (CRM-20) already use for writes into a read-side freshness check —
    deliberately two states only, not a fabricated pipeline (see module
    docstring)."""

    FRESH = "FRESH"
    STALE = "STALE"


class CacheReadDecision(str, Enum):
    """What `policies/offline_read_policy.py::resolve_cache_read` tells
    a caller to do with one cached entry. `USE_CACHE_STALE_OFFLINE` is the
    genuinely offline-first case: no connectivity, so a stale/expired
    cache is still the best available answer rather than nothing."""

    USE_CACHE_FRESH = "USE_CACHE_FRESH"
    USE_CACHE_STALE_OFFLINE = "USE_CACHE_STALE_OFFLINE"
    REFRESH_REQUIRED = "REFRESH_REQUIRED"
    NO_CACHE_AVAILABLE = "NO_CACHE_AVAILABLE"
