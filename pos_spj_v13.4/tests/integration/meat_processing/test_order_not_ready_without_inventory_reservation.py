"""§6/§7/§25 — sin reserva REAL de Inventario la orden no queda lista, y sin
estar lista no se libera. Todo o nada: no se retiene la mitad. No hay
existencia negativa.

Lomo de cerdo entero: hay 5 kg y la orden pide 10.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.meat_processing.integrations.products_recipe_snapshot_adapter import (
    ProductsRecipeSnapshotAdapter,
)
from backend.application.meat_processing.use_cases.preparation_use_cases import (
    PrepareProcessingOrderUseCase,
)
from backend.domain.meat_processing.enums import ProcessingOrderStatus, ProcessType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid
from tests.integration.meat_processing._generic_plant import Planta, build_db


@pytest.fixture()
def lomo():
    conn = build_db()
    p = Planta(conn)
    porcino = p.especie("Porcino")
    entero = p.producto("Lomo de cerdo entero", especie=porcino)
    chuleta = p.producto("Chuleta", especie=porcino)
    p.despiece(entero, [(chuleta, "MAIN_PRODUCT", "1")], especie=porcino)
    p.existencia(entero, "5")
    yield p, entero
    conn.close()


def _estado(p, oid):
    return MeatProcessingUnitOfWork(p.conn).orders.get(oid).status


def test_short_stock_leaves_the_order_waiting_and_reserves_nothing(lomo):
    p, entero = lomo
    oid = p.orden(ProcessType.CUTTING, entero, "10")

    r = p.preparar(oid)

    assert r.success and r.data["ready"] is False
    faltante = r.data["shortages"][0]
    assert (faltante["product_id"], faltante["required"], faltante["available"]) == (
        entero, "10.000", "5")
    assert _estado(p, oid) is ProcessingOrderStatus.MATERIALS_PENDING
    assert p.reservado(entero) == Decimal("0")             # todo o nada
    assert MeatProcessingUnitOfWork(p.conn).requirement_allocations.list_by_order(oid) == []


def test_a_waiting_order_cannot_be_released(lomo):
    p, entero = lomo
    oid = p.orden(ProcessType.CUTTING, entero, "10")
    p.preparar(oid)

    r = p.liberar(oid)

    assert not r.success and r.error_code == "ORDER_NOT_READY"
    assert _estado(p, oid) is ProcessingOrderStatus.MATERIALS_PENDING


def test_once_stock_arrives_preparing_again_makes_it_ready(lomo):
    p, entero = lomo
    oid = p.orden(ProcessType.CUTTING, entero, "10")
    p.preparar(oid)
    p.existencia(entero, "7")

    r = p.preparar(oid)

    assert r.success and r.data["ready"] is True
    assert _estado(p, oid) is ProcessingOrderStatus.READY
    assert p.reservado(entero) == Decimal("10")
    assert p.liberar(oid).success


def test_without_an_inventory_integration_nothing_is_ever_ready(lomo):
    """Sin puerto de reservas no se fabrica una reserva de papel."""
    p, entero = lomo
    p.existencia(entero, "20")
    oid = p.orden(ProcessType.CUTTING, entero, "10")

    r = PrepareProcessingOrderUseCase(
        p.auth(), recipe_snapshot_port=ProductsRecipeSnapshotAdapter(p.conn)).execute(
        p.conn, order_id=oid, operation_id=new_uuid(), actor_user_id=p.operario)

    assert r.success and r.data["ready"] is False
    assert _estado(p, oid) is ProcessingOrderStatus.MATERIALS_PENDING
    assert p.reservado(entero) == Decimal("0")


def test_reserved_stock_is_never_driven_negative(lomo):
    p, entero = lomo
    p.existencia(entero, "5")                                    # 10 en total
    oid = p.lista(ProcessType.CUTTING, entero, "10")
    r = p.ejecutar(oid, {entero: "12"}, entradas={entero: "12"})
    assert not r.success and r.error_code == "EXCEEDS_RESERVATION"
    assert p.saldo(entero) == Decimal("10")
    negativos = p.conn.execute(
        "SELECT COUNT(*) FROM inventory_balances WHERE CAST(quantity AS REAL) < 0").fetchone()[0]
    assert negativos == 0
