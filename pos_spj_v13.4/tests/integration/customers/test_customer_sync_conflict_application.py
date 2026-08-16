"""Customer Master offline-first sync conflicts (§91-92, CRM-20) —
DetectCustomerSyncConflictUseCase must never silently apply a stale
mutation; ResolveCustomerSyncConflictUseCase is the only path that can
close one."""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.use_cases.lifecycle_use_cases import CreateCustomerUseCase
from backend.application.customers.use_cases.sync_conflict_use_cases import (
    DetectCustomerSyncConflictUseCase,
    ResolveCustomerSyncConflictUseCase,
)
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork

_ACTOR = "user-sync-admin"


class _AllowAllForActor:
    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return user_id == self._user_id


def _admin_policy() -> CustomerAuthorizationPolicy:
    return CustomerAuthorizationPolicy(_AllowAllForActor(_ACTOR))


def _make_customer(cust_conn) -> str:
    result = CreateCustomerUseCase(_admin_policy()).execute(
        cust_conn, actor_user_id=_ACTOR, display_name="Cliente Sync", operation_id="op-create-1")
    assert result.success, result.message
    return result.entity_id


class TestDetectCustomerSyncConflict:
    def test_matching_version_reports_no_conflict(self, cust_conn):
        customer_id = _make_customer(cust_conn)
        result = DetectCustomerSyncConflictUseCase().execute(
            cust_conn, customer_id=customer_id, base_version=1, remote_snapshot={},
            operation_id="op-detect-1")
        assert result.success
        assert result.data["conflict"] is False

    def test_stale_version_creates_conflict_and_blocks(self, cust_conn):
        customer_id = _make_customer(cust_conn)
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = uow.customers.get(customer_id)
            customer.display_name = "Editado localmente"
            customer.record_edit()
            uow.customers.update(customer)
        assert customer.version == 2

        result = DetectCustomerSyncConflictUseCase().execute(
            cust_conn, customer_id=customer_id, base_version=1,
            remote_snapshot={"display_name": "Editado remotamente"}, operation_id="op-detect-2")

        assert not result.success
        assert result.error_code == "SYNC_CONFLICT"
        assert result.data["conflict"] is True
        with CustomerUnitOfWork(cust_conn) as uow:
            still_local = uow.customers.get(customer_id)
            conflicts = uow.sync_conflicts.list_open_for_customer(customer_id)
        # The remote change was never applied — local edit survives untouched.
        assert still_local.display_name == "Editado localmente"
        assert len(conflicts) == 1
        assert conflicts[0].id == result.data["conflict_id"]
        assert conflicts[0].remote_snapshot == {"display_name": "Editado remotamente"}


class TestResolveCustomerSyncConflict:
    def _detect(self, cust_conn, customer_id):
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = uow.customers.get(customer_id)
            customer.display_name = "Editado localmente"
            customer.record_edit()
            uow.customers.update(customer)
        result = DetectCustomerSyncConflictUseCase().execute(
            cust_conn, customer_id=customer_id, base_version=1,
            remote_snapshot={"display_name": "Editado remotamente"}, operation_id="op-detect-x")
        return result.data["conflict_id"]

    def test_resolve_denied_without_permission(self, cust_conn):
        customer_id = _make_customer(cust_conn)
        conflict_id = self._detect(cust_conn, customer_id)
        result = ResolveCustomerSyncConflictUseCase(CustomerAuthorizationPolicy()).execute(
            cust_conn, actor_user_id=_ACTOR, conflict_id=conflict_id, resolution="LOCAL",
            operation_id="op-resolve-denied")
        assert not result.success
        assert result.error_code == "PERMISSION_DENIED"

    def test_resolve_local_keeps_local_data(self, cust_conn):
        customer_id = _make_customer(cust_conn)
        conflict_id = self._detect(cust_conn, customer_id)
        result = ResolveCustomerSyncConflictUseCase(_admin_policy()).execute(
            cust_conn, actor_user_id=_ACTOR, conflict_id=conflict_id, resolution="LOCAL",
            operation_id="op-resolve-local")
        assert result.success
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = uow.customers.get(customer_id)
            conflict = uow.sync_conflicts.get(conflict_id)
        assert customer.display_name == "Editado localmente"
        assert conflict.status.value == "RESOLVED_LOCAL"
        assert conflict.resolved_by_user_id == _ACTOR

    def test_resolve_remote_applies_remote_snapshot(self, cust_conn):
        customer_id = _make_customer(cust_conn)
        conflict_id = self._detect(cust_conn, customer_id)
        result = ResolveCustomerSyncConflictUseCase(_admin_policy()).execute(
            cust_conn, actor_user_id=_ACTOR, conflict_id=conflict_id, resolution="REMOTE",
            operation_id="op-resolve-remote")
        assert result.success
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = uow.customers.get(customer_id)
        assert customer.display_name == "Editado remotamente"
        assert customer.version == 3  # 1 (create) -> 2 (local edit) -> 3 (resolution applies)

    def test_resolve_merged_applies_caller_supplied_fields(self, cust_conn):
        customer_id = _make_customer(cust_conn)
        conflict_id = self._detect(cust_conn, customer_id)
        result = ResolveCustomerSyncConflictUseCase(_admin_policy()).execute(
            cust_conn, actor_user_id=_ACTOR, conflict_id=conflict_id, resolution="MERGED",
            merged_fields={"display_name": "Fusionado a mano"}, operation_id="op-resolve-merged")
        assert result.success
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = uow.customers.get(customer_id)
        assert customer.display_name == "Fusionado a mano"

    def test_cannot_resolve_already_resolved_conflict_twice(self, cust_conn):
        customer_id = _make_customer(cust_conn)
        conflict_id = self._detect(cust_conn, customer_id)
        ResolveCustomerSyncConflictUseCase(_admin_policy()).execute(
            cust_conn, actor_user_id=_ACTOR, conflict_id=conflict_id, resolution="LOCAL",
            operation_id="op-first")
        result = ResolveCustomerSyncConflictUseCase(_admin_policy()).execute(
            cust_conn, actor_user_id=_ACTOR, conflict_id=conflict_id, resolution="REMOTE",
            operation_id="op-second")
        assert not result.success
        assert result.error_code == "VALIDATION"
