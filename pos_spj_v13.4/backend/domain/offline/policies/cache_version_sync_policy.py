"""CacheVersionSyncPolicy — SET-23 "Sync": does an `OfflineCacheEntry`
still reflect the origin's current version? Generalizes the version/
`updated_at` comparison
`DetectCustomerSyncConflictUseCase`/`DetectCRMSyncConflictUseCase`
(`docs/refactor/CRM-20_offline_sync_conflictos.md`) already use to guard
writes into a read-side freshness check — a plain string comparison, no
fabricated multi-stage sync pipeline (see `enums.py`'s module docstring
for why).
"""

from __future__ import annotations

from backend.domain.offline.entities.offline_cache_entry import OfflineCacheEntry
from backend.domain.offline.enums import CacheSyncState


def evaluate_sync_state(entry: OfflineCacheEntry, origin_version: str) -> CacheSyncState:
    return CacheSyncState.FRESH if entry.source_version == origin_version else CacheSyncState.STALE
