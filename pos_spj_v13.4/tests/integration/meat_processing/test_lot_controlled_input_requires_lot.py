"""§8/§25 — un insumo controlado por lote (dato de Productos, no de la especie)
se reserva y se consume SIEMPRE con lote. La existencia sin lote de ese producto
no es elegible.

Canal bovina controlada por lote.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.meat_processing.use_cases import (
    CaptureMaterialConsumptionUseCase,
    PostMaterialConsumptionUseCase,
    StartProcessExecutionUseCase,
)
from backend.domain.meat_processing.enums import ProcessType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid
from tests.integration.meat_processing._generic_plant import Planta, build_db


@pytest.fixture()
def canal():
    conn = build_db()
    p = Planta(conn)
    bovino = p.especie("Bovino")
    fuente = p.producto("Canal bovina", lote=True, especie=bovino)
    pierna = p.producto("Pierna", especie=bovino)
    p.despiece(fuente, [(pierna, "MAIN_PRODUCT", "1")], especie=bovino)
    yield p, fuente, pierna
    conn.close()


def test_stock_without_lot_is_not_eligible_for_a_lot_controlled_input(canal):
    p, fuente, _ = canal
    p.existencia(fuente, "300")                                   # sin lote
    oid = p.orden(ProcessType.DISASSEMBLY, fuente, "100")

    r = p.preparar(oid)

    assert r.data["ready"] is False
    assert p.reservado(fuente) == Decimal("0")


def test_the_reservation_and_the_consumption_carry_the_lot(canal):
    p, fuente, pierna = canal
    lote = p.existencia(fuente, "300", lote="CANAL-44", vence="2031-04-01")
    p.costo(fuente, "95")
    oid = p.lista(ProcessType.DISASSEMBLY, fuente, "100")

    uow = MeatProcessingUnitOfWork(p.conn)
    assert [a.allocated_lot_id for a in uow.requirement_allocations.list_by_order(oid)] == [lote]
    requerimiento = uow.material_requirements.list_by_order(oid)[0]
    assert requerimiento.lot_required is True

    assert p.ejecutar(oid, {pierna: "100"}).success
    consumos = MeatProcessingUnitOfWork(p.conn).consumptions.list_by_order(oid)
    assert [c.lot_id for c in consumos] == [lote]
    salida = p.conn.execute(
        "SELECT l.lot_id FROM inventory_ledger_lines l JOIN inventory_ledger m"
        " ON m.id = l.movement_id WHERE m.movement_type='PRODUCTION_CONSUMPTION'"
        " AND m.source_document_id=?", (oid,)).fetchall()
    assert [r[0] for r in salida] == [lote]


def test_posting_a_consumption_without_lot_is_refused(canal):
    p, fuente, _ = canal
    p.existencia(fuente, "300", lote="CANAL-44", vence="2031-04-01")
    oid = p.lista(ProcessType.DISASSEMBLY, fuente, "100")
    assert StartProcessExecutionUseCase(p.auth()).execute(
        p.conn, order_id=oid, operation_id=new_uuid(), actor_user_id=p.operario).success
    capturado = CaptureMaterialConsumptionUseCase(p.auth()).execute(
        p.conn, order_id=oid, operation_id=new_uuid(), product_id=fuente,
        warehouse_id=p.warehouse, planned_quantity=Decimal("0"),
        planned_weight=Decimal("100"), actual_quantity=Decimal("0"),
        actual_weight=Decimal("100"), actor_user_id=p.operario)
    assert capturado.success, capturado.message

    class _NoDebeLlamarse:
        def post_consumption(self, **kwargs):
            raise AssertionError("no se descuenta existencia sin lote")

    r = PostMaterialConsumptionUseCase(p.auth(), inventory_port=_NoDebeLlamarse()).execute(
        p.conn, consumption_id=capturado.entity_id, operation_id=new_uuid(),
        actor_user_id=p.operario)
    assert not r.success and r.error_code == "LOT_REQUIRED"
