"""ASSET-21 — AssetSyncConflict (offline-first vocabulary only; no real sync
engine wiring exists yet — see the entity's own module docstring)."""

import pytest

from backend.domain.assets.entities.asset_sync_conflict import AssetSyncConflict
from backend.domain.assets.enums import AssetSyncConflictStatus, AssetSyncConflictType
from backend.domain.assets.exceptions import (
    AssetDomainError,
    AssetSyncConflictAlreadyResolvedError,
)


def _conflict(**extra) -> AssetSyncConflict:
    return AssetSyncConflict.create(
        "asset-1", AssetSyncConflictType.CUSTODY_CHANGED, "op-local", "op-remote",
        '{"custodian_user_id": "u1"}', '{"custodian_user_id": "u2"}', **extra)


class TestAssetSyncConflictCreate:
    def test_create_ok(self):
        c = _conflict()
        assert c.is_open() is True

    def test_same_operation_id_is_not_a_conflict(self):
        with pytest.raises(AssetDomainError):
            AssetSyncConflict.create(
                "asset-1", AssetSyncConflictType.CUSTODY_CHANGED, "op-1", "op-1", "{}", "{}")


class TestAssetSyncConflictResolution:
    def test_keep_local(self):
        c = _conflict()
        c.keep_local("resolver-1", "el dispositivo local tenía la captura más reciente")
        assert c.status is AssetSyncConflictStatus.RESOLVED_KEEP_LOCAL
        assert c.is_open() is False

    def test_keep_remote(self):
        c = _conflict()
        c.keep_remote("resolver-1")
        assert c.status is AssetSyncConflictStatus.RESOLVED_KEEP_REMOTE

    def test_resolve_merged(self):
        c = _conflict()
        c.resolve_merged("resolver-1", "se combinaron ambos cambios")
        assert c.status is AssetSyncConflictStatus.RESOLVED_MERGED

    def test_cannot_resolve_twice(self):
        c = _conflict()
        c.keep_local("resolver-1")
        with pytest.raises(AssetSyncConflictAlreadyResolvedError):
            c.keep_remote("resolver-2")

    def test_resolution_requires_a_resolver(self):
        c = _conflict()
        with pytest.raises(AssetDomainError):
            c.keep_local("")
