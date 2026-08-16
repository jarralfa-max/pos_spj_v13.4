"""CustomerSyncConflict domain entity tests (CRM-20, §92)."""

from __future__ import annotations

import pytest

from backend.domain.customers.entities.customer_sync_conflict import CustomerSyncConflict
from backend.domain.customers.enums import CustomerSyncConflictType, SyncConflictStatus
from backend.domain.customers.exceptions import CustomerSyncConflictAlreadyResolvedError


def _make_conflict() -> CustomerSyncConflict:
    return CustomerSyncConflict.detect(
        "cust-1", CustomerSyncConflictType.CUSTOMER_UPDATED_REMOTELY, 1,
        {"display_name": "Remote"}, operation_id="op-1")


class TestCustomerSyncConflictDetect:
    def test_detect_starts_open(self):
        conflict = _make_conflict()
        assert conflict.status == SyncConflictStatus.OPEN
        assert conflict.resolved_at is None
        assert conflict.remote_snapshot == {"display_name": "Remote"}


class TestCustomerSyncConflictResolve:
    def test_resolve_sets_status_and_metadata(self):
        conflict = _make_conflict()
        conflict.resolve(SyncConflictStatus.RESOLVED_LOCAL, resolved_by_user_id="user-1",
                         resolution_note="kept local")
        assert conflict.status == SyncConflictStatus.RESOLVED_LOCAL
        assert conflict.resolved_by_user_id == "user-1"
        assert conflict.resolution_note == "kept local"
        assert conflict.resolved_at is not None

    def test_cannot_resolve_twice(self):
        conflict = _make_conflict()
        conflict.resolve(SyncConflictStatus.RESOLVED_LOCAL, resolved_by_user_id="user-1")
        with pytest.raises(CustomerSyncConflictAlreadyResolvedError):
            conflict.resolve(SyncConflictStatus.RESOLVED_REMOTE, resolved_by_user_id="user-2")

    def test_cannot_resolve_to_open(self):
        conflict = _make_conflict()
        with pytest.raises(CustomerSyncConflictAlreadyResolvedError):
            conflict.resolve(SyncConflictStatus.OPEN, resolved_by_user_id="user-1")
