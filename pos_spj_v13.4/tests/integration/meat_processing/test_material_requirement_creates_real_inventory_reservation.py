"""§6/§25 — preparar crea reservas REALES en Inventario: cada una retiene un
saldo exacto (lote y ubicación) y queda ligada al requerimiento.

Pescado entero en dos lotes con caducidades distintas: Inventario elige con la
estrategia que tenga configurada (FEFO si nada), no Procesamiento.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from backend.domain.meat_processing.enums import MaterialRequirementStatus, ProcessType
from backend.infrastructure.db.repositories.inventory.support_repositories import (
    InventorySettingsRepository,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import is_uuidv7
from tests.integration.meat_processing._generic_plant import Planta, build_db


@pytest.fixture()
def pescado():
    conn = build_db()
    p = Planta(conn)
    marino = p.especie("Pescado")
    entero = p.producto("Huachinango entero", lote=True, especie=marino)
    filete = p.producto("Filete de huachinango", lote=True, especie=marino)
    espinas = p.producto("Espinas", especie=marino)
    p.despiece(entero, [(filete, "MAIN_PRODUCT", "0.45"), (espinas, "WASTE", "0.55")],
               especie=marino)
    tardio = p.existencia(entero, "6", lote="LOTE-TARDIO", vence="2031-03-01")
    pronto = p.existencia(entero, "6", lote="LOTE-PRONTO", vence="2031-01-01")
    yield p, entero, tardio, pronto
    conn.close()


def _reservas(conn, order_id):
    return [dict(r) for r in conn.execute(
        "SELECT r.* FROM inventory_reservation r JOIN material_requirement_allocations a"
        " ON a.inventory_reservation_id = r.id WHERE a.processing_order_id=?"
        " ORDER BY r.created_at, r.id", (order_id,)).fetchall()]


def test_each_allocation_holds_a_real_reservation_on_an_exact_lot_and_location(pescado):
    p, entero, tardio, pronto = pescado
    oid = p.lista(ProcessType.DISASSEMBLY, entero, "8")

    uow = MeatProcessingUnitOfWork(p.conn)
    asignaciones = uow.requirement_allocations.list_by_order(oid)
    reservas = {r["id"]: r for r in _reservas(p.conn, oid)}
    assert len(asignaciones) == 2 and set(reservas) == {
        a.inventory_reservation_id for a in asignaciones}
    for a in asignaciones:
        r = reservas[a.inventory_reservation_id]
        assert r["source"] == "PRODUCTION_ORDER"
        assert (r["lot_id"], r["location_id"]) == (a.allocated_lot_id, a.allocated_location_id)
        assert Decimal(r["quantity"]) == a.quantity
        assert a.allocated_location_id == p.ubicacion
        assert is_uuidv7(a.inventory_reservation_id) and is_uuidv7(r["operation_id"])
    requerimiento = uow.material_requirements.list_by_order(oid)[0]
    assert requerimiento.status is MaterialRequirementStatus.ALLOCATED


def test_without_configuration_inventory_allocates_first_expired_first(pescado):
    p, entero, tardio, pronto = pescado
    oid = p.lista(ProcessType.DISASSEMBLY, entero, "8")
    por_lote = {a.allocated_lot_id: a.quantity for a in
                MeatProcessingUnitOfWork(p.conn).requirement_allocations.list_by_order(oid)}
    assert por_lote == {pronto: Decimal("6"), tardio: Decimal("2")}


def test_the_strategy_is_what_inventory_has_configured_for_the_warehouse(pescado):
    p, entero, tardio, pronto = pescado
    InventorySettingsRepository(p.conn).set(
        setting_key="production.allocation_strategy", setting_value="FIFO",
        scope_type="WAREHOUSE", scope_id=p.warehouse)
    p.conn.commit()
    oid = p.lista(ProcessType.DISASSEMBLY, entero, "8")
    por_lote = {a.allocated_lot_id: a.quantity for a in
                MeatProcessingUnitOfWork(p.conn).requirement_allocations.list_by_order(oid)}
    assert por_lote == {tardio: Decimal("6"), pronto: Decimal("2")}   # el que llegó primero


def test_the_reservation_is_visible_as_reserved_stock_and_announced(pescado):
    p, entero, _, _ = pescado
    oid = p.lista(ProcessType.DISASSEMBLY, entero, "8")
    assert p.reservado(entero) == Decimal("8")
    assert p.saldo(entero) == Decimal("12")                # nada se consumió todavía
    eventos = [json.loads(r["payload_json"]) for r in
               MeatProcessingUnitOfWork(p.conn).outbox.list_pending()
               if r["event_name"] == "PROCESSING_MATERIAL_RESERVED"]
    assert len(eventos) == 1
    assert set(eventos[0]["inventory_reservation_ids"]) == {
        r["id"] for r in _reservas(p.conn, oid)}
