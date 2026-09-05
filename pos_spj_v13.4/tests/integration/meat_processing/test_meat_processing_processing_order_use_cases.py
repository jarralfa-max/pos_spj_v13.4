"""PROC-6 e2e: create → approve → release, snapshot capture, idempotency,
permission and scope enforcement."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.authorization import (
    DenyAllMeatProcessingPermissionCheckerForTests,
    MeatProcessingAuthorizationPolicy,
)
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.ports import RecipeSnapshot
from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    CreateProcessingOrderUseCase,
    ReleaseProcessingOrderUseCase,
)
from backend.domain.meat_processing.enums import ProcessingOrderStatus, ProcessType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema"
    ).run(c)
    yield c
    c.close()


def _create(conn, **overrides):
    kwargs = dict(
        operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
        process_type=ProcessType.CUTTING, target_product_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("100"),
        actor_user_id=new_uuid())
    kwargs.update(overrides)
    return CreateProcessingOrderUseCase().execute(conn, **kwargs)


class TestCreate:
    def test_create_submits_for_approval_by_default(self, conn):
        result = _create(conn)
        assert result.success
        assert result.data["status"] == ProcessingOrderStatus.PENDING_APPROVAL.value

    def test_create_without_submit_stays_draft(self, conn):
        result = _create(conn, submit_for_approval=False)
        assert result.success
        assert result.data["status"] == ProcessingOrderStatus.DRAFT.value

    def test_create_is_idempotent_on_operation_id(self, conn):
        op_id = new_uuid()
        first = _create(conn, operation_id=op_id)
        second = _create(conn, operation_id=op_id, target_product_id=new_uuid())
        assert second.entity_id == first.entity_id
        assert second.data["already_processed"] is True

    def test_create_denies_without_permission(self, conn):
        deny = CreateProcessingOrderUseCase(
            MeatProcessingAuthorizationPolicy(DenyAllMeatProcessingPermissionCheckerForTests()))
        result = deny.execute(
            conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
            process_type=ProcessType.CUTTING, target_product_id=new_uuid(),
            planned_quantity=Decimal("1"), planned_weight=Decimal("1"),
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "PERMISSION_DENIED"

    def test_create_enforces_branch_scope(self, conn):
        branch_id = new_uuid()
        context = MeatProcessingExecutionContext(
            actor_user_id="actor", active_branch_id=branch_id)
        result = _create(conn, branch_id=new_uuid(), actor_user_id="actor", context=context)
        assert not result.success
        assert result.error_code == "SCOPE_DENIED"

    def test_audit_and_outbox_are_recorded_on_create(self, conn):
        result = _create(conn)
        with MeatProcessingUnitOfWork(conn) as uow:
            entries = uow.audit.list_for_entity("ProcessingOrder", result.entity_id)
            assert any(entry["action"] == "CREATED" for entry in entries)
            pending = uow.outbox.list_pending()
            assert any(row["operation_id"] == result.operation_id for row in pending)


class TestApprove:
    def _approved_order_id(self, conn):
        return _create(conn).entity_id

    def test_approve_happy_path(self, conn):
        order_id = self._approved_order_id(conn)
        result = ApproveProcessingOrderUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.orders.get(order_id).status is ProcessingOrderStatus.APPROVED

    def test_approve_is_idempotent(self, conn):
        order_id = self._approved_order_id(conn)
        ApproveProcessingOrderUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        second = ApproveProcessingOrderUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert second.success
        assert second.data["already_processed"] is True

    def test_approve_rejects_self_approval(self, conn):
        creator = new_uuid()
        order_id = _create(conn, actor_user_id=creator).entity_id
        result = ApproveProcessingOrderUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=creator)
        assert not result.success
        assert result.error_code == "SEGREGATION_OF_DUTIES"

    def test_approve_unknown_order_fails(self, conn):
        result = ApproveProcessingOrderUseCase().execute(
            conn, order_id=new_uuid(), operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "ORDER_NOT_FOUND"


class TestRelease:
    def _approved_order_id(self, conn, **create_overrides):
        order_id = _create(conn, **create_overrides).entity_id
        ApproveProcessingOrderUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        return order_id

    def test_release_without_snapshot_port_leaves_version_ids_none(self, conn):
        order_id = self._approved_order_id(conn)
        result = ReleaseProcessingOrderUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            order = uow.orders.get(order_id)
            assert order.status is ProcessingOrderStatus.RELEASED
            assert order.recipe_version_id is None

    def test_release_captures_recipe_snapshot_and_audits_it(self, conn):
        order_id = self._approved_order_id(conn)
        recipe_id = new_uuid()

        class FakePort:
            def resolve(self, *, target_product_id, process_type):
                return RecipeSnapshot(
                    recipe_version_id=recipe_id,
                    components=({"product_id": new_uuid(), "quantity": "1"},),
                    yield_tolerances={"warning_pct": "2"})

        result = ReleaseProcessingOrderUseCase(recipe_snapshot_port=FakePort()).execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            order = uow.orders.get(order_id)
            assert order.recipe_version_id == recipe_id
            entries = uow.audit.list_for_entity("ProcessingOrder", order_id)
            snapshot_entries = [e for e in entries if e["action"] == "RECIPE_SNAPSHOT_CAPTURED"]
            assert len(snapshot_entries) == 1

    def test_release_is_idempotent_and_does_not_recapture_snapshot(self, conn):
        order_id = self._approved_order_id(conn)
        calls = {"count": 0}

        class CountingPort:
            def resolve(self, *, target_product_id, process_type):
                calls["count"] += 1
                return RecipeSnapshot(recipe_version_id=new_uuid())

        port = CountingPort()
        ReleaseProcessingOrderUseCase(recipe_snapshot_port=port).execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        second = ReleaseProcessingOrderUseCase(recipe_snapshot_port=port).execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert second.success
        assert second.data["already_processed"] is True
        assert calls["count"] == 1

    def test_release_unknown_order_fails(self, conn):
        result = ReleaseProcessingOrderUseCase().execute(
            conn, order_id=new_uuid(), operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "ORDER_NOT_FOUND"

    def test_release_before_approval_is_rejected(self, conn):
        order_id = _create(conn, submit_for_approval=False).entity_id
        result = ReleaseProcessingOrderUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "MEAT_PROCESSING_RULE_VIOLATION"


class TestFullLifecycle:
    def test_create_approve_release_round_trip(self, conn):
        creator, approver, releaser = new_uuid(), new_uuid(), new_uuid()
        created = _create(conn, actor_user_id=creator)
        approved = ApproveProcessingOrderUseCase().execute(
            conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=approver)
        assert approved.success
        released = ReleaseProcessingOrderUseCase().execute(
            conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=releaser)
        assert released.success
        with MeatProcessingUnitOfWork(conn) as uow:
            order = uow.orders.get(created.entity_id)
            assert order.status is ProcessingOrderStatus.RELEASED
            assert order.approved_by_user_id == approver
            assert order.released_by_user_id == releaser
