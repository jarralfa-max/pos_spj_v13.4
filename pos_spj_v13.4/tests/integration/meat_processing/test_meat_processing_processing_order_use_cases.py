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
from tests.integration.meat_processing._generic_plant import build_db, released_order


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema"
    ).run(c)
    importlib.import_module(
        "migrations.standalone.272_meat_processing_frozen_definition_and_real_reservations"
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
    """Sólo una orden PREPARADA se libera: definición congelada al preparar e
    insumos reservados en Inventario. Liberar no vuelve a leer Productos."""

    def _approved_order_id(self, conn, **create_overrides):
        order_id = _create(conn, **create_overrides).entity_id
        ApproveProcessingOrderUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        return order_id

    def test_an_approved_but_unprepared_order_is_not_released(self, conn):
        order_id = self._approved_order_id(conn)
        result = ReleaseProcessingOrderUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "ORDER_NOT_READY"
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.orders.get(order_id).status is ProcessingOrderStatus.APPROVED

    def test_ready_without_a_frozen_definition_is_not_released(self, conn):
        """Datos heredados: READY sin foto congelada. No se libera a ciegas."""
        order_id = self._approved_order_id(conn)
        with MeatProcessingUnitOfWork(conn) as uow:
            order = uow.orders.get(order_id)
            order.mark_ready()
            uow.orders.save(order)
        result = ReleaseProcessingOrderUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "MASTER_DATA_MISSING"

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
        assert result.error_code == "ORDER_NOT_READY"


class TestFullLifecycle:
    def test_create_approve_prepare_release_round_trip(self):
        conn = build_db()
        planta, order_id, _ = released_order(conn)
        with MeatProcessingUnitOfWork(conn) as uow:
            order = uow.orders.get(order_id)
            snapshot = uow.recipe_snapshots.get_by_order(order_id)
            assert order.status is ProcessingOrderStatus.RELEASED
            assert order.approved_by_user_id == planta.gerente
            assert order.released_by_user_id == planta.operario
            acciones = [e["action"] for e in uow.audit.list_for_entity("ProcessingOrder",
                                                                        order_id)]
            eventos = {r["event_name"]: r for r in uow.outbox.list_pending()}
        assert snapshot is not None and snapshot.is_frozen
        assert "RECIPE_SNAPSHOT_CAPTURED" in acciones and "RELEASED" in acciones
        assert snapshot.id in eventos["PROCESSING_ORDER_RELEASED"]["payload_json"]

    def test_release_is_idempotent(self):
        conn = build_db()
        planta, order_id, _ = released_order(conn)
        again = planta.liberar(order_id)
        assert again.success and again.data["already_processed"] is True
