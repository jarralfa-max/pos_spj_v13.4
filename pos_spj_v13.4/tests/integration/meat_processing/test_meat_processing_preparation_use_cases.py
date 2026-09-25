"""PROC-7 e2e: preparación de la orden y asignación de operadores.

Preparar = congelar la definición productiva + reservar los insumos en
Inventario (reserva REAL: lote y ubicación exactos). Las reservas reales y el
"no READY sin reserva" se prueban en
`test_material_requirement_creates_real_inventory_reservation.py` y
`test_order_not_ready_without_inventory_reservation.py`; aquí, el ciclo de
estados de la preparación y los operadores."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.use_cases import (
    AssignOperatorUseCase,
    CreateProcessingOrderUseCase,
    ReleaseOperatorAssignmentUseCase,
)
from backend.domain.meat_processing.enums import OperatorRole, ProcessingOrderStatus, ProcessType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid
from tests.integration.meat_processing._generic_plant import Planta, build_db, released_order


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema").run(c)
    importlib.import_module(
        "migrations.standalone.248_meat_processing_preparation_execution_schema").run(c)
    yield c
    c.close()


@pytest.fixture
def approved_order_id(conn):
    created = CreateProcessingOrderUseCase().execute(
        conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
        process_type=ProcessType.CUTTING, target_product_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("100"),
        actor_user_id=new_uuid())
    from backend.application.meat_processing.use_cases import ApproveProcessingOrderUseCase
    ApproveProcessingOrderUseCase().execute(
        conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
    return created.entity_id


class TestOperatorAssignment:
    def test_assign_and_release(self, conn, approved_order_id):
        assigned = AssignOperatorUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), user_id=new_uuid(),
            role_type=OperatorRole.CUTTER, actor_user_id=new_uuid())
        assert assigned.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.operator_assignments.get(assigned.entity_id).is_active

        released = ReleaseOperatorAssignmentUseCase().execute(
            conn, assignment_id=assigned.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert released.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert not uow.operator_assignments.get(assigned.entity_id).is_active

    def test_release_is_idempotent(self, conn, approved_order_id):
        assigned = AssignOperatorUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), user_id=new_uuid(),
            role_type=OperatorRole.WEIGHER, actor_user_id=new_uuid())
        ReleaseOperatorAssignmentUseCase().execute(
            conn, assignment_id=assigned.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        second = ReleaseOperatorAssignmentUseCase().execute(
            conn, assignment_id=assigned.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert second.data["already_processed"] is True


class TestPrepare:
    def test_an_order_that_is_not_approved_cannot_be_prepared(self):
        conn = build_db()
        planta = Planta(conn)
        creada = CreateProcessingOrderUseCase(planta.auth()).execute(
            conn, operation_id=new_uuid(), branch_id=planta.branch,
            warehouse_id=planta.warehouse, process_type=ProcessType.CUTTING,
            target_product_id=planta.producto("Insumo"), planned_quantity=Decimal("0"),
            planned_weight=Decimal("10"), actor_user_id=planta.operario,
            submit_for_approval=False)
        r = planta.preparar(creada.entity_id)
        assert not r.success and r.error_code == "INVALID_STATE"

    def test_preparing_twice_does_not_reserve_twice(self):
        conn = build_db()
        planta, order_id, insumo = released_order(conn, peso="40")
        # Ya liberada: volver a preparar no aplica (no está aprobada ni lista)...
        assert planta.preparar(order_id).error_code == "INVALID_STATE"
        assert planta.reservado(insumo) == Decimal("40")

        # ...y una orden READY es idempotente: misma reserva.
        oid = planta.orden(ProcessType.CUTTING, insumo, "10")
        assert planta.preparar(oid).data["ready"] is True
        again = planta.preparar(oid)
        assert again.success and again.data["already_processed"] is True
        assert planta.reservado(insumo) == Decimal("50")
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.orders.get(oid).status is ProcessingOrderStatus.READY
            assert len(uow.requirement_allocations.list_by_order(oid)) == 1
