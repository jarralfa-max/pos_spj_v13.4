"""§9/§25 — Procesamiento nunca usa la sucursal como ubicación. Toda reserva,
consumo y recepción cae en una ubicación REAL del almacén, resuelta por
Inventario; si el almacén no tiene dónde recibir, se falla claro.

Mezcla de carne (formulación) y despiece de canal, mismo criterio.
"""
from __future__ import annotations

import pytest

from backend.application.inventory.queries.stock_location_resolver import (
    StockLocationNotConfiguredError,
    StockLocationResolver,
)
from backend.domain.meat_processing.enums import ProcessType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid
from tests.integration.meat_processing._generic_plant import Planta, build_db


def _ubicaciones_del_almacen(p):
    return {r[0] for r in p.conn.execute(
        "SELECT id FROM storage_locations WHERE warehouse_id=?", (p.warehouse,)).fetchall()}


def _ubicaciones_tocadas(p, oid):
    filas = p.conn.execute(
        "SELECT l.from_location_id, l.to_location_id FROM inventory_ledger_lines l"
        " JOIN inventory_ledger m ON m.id = l.movement_id WHERE m.source_document_id=?",
        (oid,)).fetchall()
    return {u for f in filas for u in f if u}


@pytest.fixture()
def planta():
    conn = build_db()
    yield Planta(conn)
    conn.close()


def test_a_formulation_reserves_consumes_and_receives_in_real_locations(planta):
    p = planta
    res = p.producto("Carne de res")
    grasa = p.producto("Grasa de cerdo")
    mezcla = p.producto("Mezcla para hamburguesa", lote=True)
    p.receta(mezcla, [(res, "0.8"), (grasa, "0.2")])
    p.existencia(res, "50"); p.existencia(grasa, "10")
    p.costo(res, "130"); p.costo(grasa, "40")

    oid = p.lista(ProcessType.MIXING, mezcla, "20")
    assert p.ejecutar(oid, {mezcla: "20"}).success

    reales = _ubicaciones_del_almacen(p)
    asignaciones = MeatProcessingUnitOfWork(p.conn).requirement_allocations.list_by_order(oid)
    assert {a.allocated_location_id for a in asignaciones} <= reales
    tocadas = _ubicaciones_tocadas(p, oid)
    assert tocadas and tocadas <= reales
    assert p.branch not in tocadas and p.warehouse not in tocadas
    salida = p.salida(oid, mezcla)
    assert salida.location_id in reales


def test_a_disassembly_output_goes_where_that_product_already_lives(planta):
    """Inventario pone la salida donde ya hay existencia disponible de ese
    producto en el almacén; si no hay, en la ubicación técnica de disponible."""
    p = planta
    especie = p.especie("Bovino")
    canal = p.producto("Canal bovina", especie=especie)
    pulpa = p.producto("Pulpa", especie=especie)
    p.despiece(canal, [(pulpa, "MAIN_PRODUCT", "1")], especie=especie)
    p.existencia(canal, "100")
    p.costo(canal, "90")
    oid = p.lista(ProcessType.DISASSEMBLY, canal, "40")
    assert p.ejecutar(oid, {pulpa: "40"}).success
    assert p.salida(oid, pulpa).location_id == p.ubicacion


def test_a_warehouse_without_locations_fails_clearly_instead_of_using_the_branch(planta):
    sin_ubicaciones = new_uuid()
    with pytest.raises(StockLocationNotConfiguredError):
        StockLocationResolver(planta.conn).available_location(
            product_id=new_uuid(), branch_id=planta.branch, warehouse_id=sin_ubicaciones)
