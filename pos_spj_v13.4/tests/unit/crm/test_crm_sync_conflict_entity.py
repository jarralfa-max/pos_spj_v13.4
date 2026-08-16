"""CRMSyncConflict domain entity tests (CRM-20, §92)."""

from __future__ import annotations

import pytest

from backend.domain.crm.entities.crm_sync_conflict import CRMSyncConflict
from backend.domain.crm.enums import CRMSyncConflictType, SyncConflictStatus
from backend.domain.crm.exceptions import CRMSyncConflictAlreadyResolvedError


def _make_conflict() -> CRMSyncConflict:
    return CRMSyncConflict.detect(
        "LEAD", "lead-1", CRMSyncConflictType.LEAD_ASSIGNMENT_CONFLICT,
        "2026-01-01T00:00:00+00:00", {"assigned_user_id": "user-remote"}, operation_id="op-1")


class TestCRMSyncConflictDetect:
    def test_detect_starts_open(self):
        conflict = _make_conflict()
        assert conflict.status == SyncConflictStatus.OPEN
        assert conflict.related_entity_type == "LEAD"


class TestCRMSyncConflictResolve:
    def test_resolve_sets_status_and_metadata(self):
        conflict = _make_conflict()
        conflict.resolve(SyncConflictStatus.RESOLVED_MERGED, resolved_by_user_id="user-1",
                         resolution_note="merged manually")
        assert conflict.status == SyncConflictStatus.RESOLVED_MERGED
        assert conflict.resolved_by_user_id == "user-1"

    def test_cannot_resolve_twice(self):
        conflict = _make_conflict()
        conflict.resolve(SyncConflictStatus.RESOLVED_LOCAL, resolved_by_user_id="user-1")
        with pytest.raises(CRMSyncConflictAlreadyResolvedError):
            conflict.resolve(SyncConflictStatus.RESOLVED_REMOTE, resolved_by_user_id="user-2")
