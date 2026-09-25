"""§12/§25 — Procesamiento no calcula costos. Registra hechos físicos y pide el
costeo; Costos decide método, valuación y reparto. Si Costos no puede costear,
Procesamiento no inventa un costo: no ejecuta."""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.meat_processing.enums import ProcessType
from backend.infrastructure.db.repositories.costing.processing_cost_repository import (
    ProcessingCostRepository,
)
from backend.infrastructure.db.repositories.inventory.support_repositories import (
    InventorySettingsRepository,
)
from tests.integration.meat_processing._generic_plant import Planta, build_db


@pytest.fixture()
def lomo():
    conn = build_db()
    p = Planta(conn)
    porcino = p.especie("Porcino")
    entero = p.producto("Lomo de cerdo entero", especie=porcino)
    chuleta = p.producto("Chuleta", especie=porcino)
    recorte = p.producto("Recorte", especie=porcino)
    p.despiece(entero, [(chuleta, "MAIN_PRODUCT", "0.7"), (recorte, "CO_PRODUCT", "0.3")],
               especie=porcino)
    p.costo(entero, "80")
    p.precio(chuleta, "150"); p.precio(recorte, "60")
    p.existencia(entero, "50")
    yield p, entero, chuleta, recorte
    conn.close()


def test_processing_results_hold_no_cost(lomo):
    p, entero, chuleta, recorte = lomo
    oid = p.lista(ProcessType.CUTTING, entero, "10")
    r = p.ejecutar(oid, {chuleta: "7", recorte: "3"})
    assert r.success
    columnas = {c[1] for c in p.conn.execute("PRAGMA table_info(processing_output_results)")}
    assert not columnas & {"allocated_cost", "unit_cost", "input_unit_cost", "unit_price"}
    assert all("cost" not in k for fila in r.data["results"] for k in fila)
    assert r.data["cost_allocation_reference"] == \
        ProcessingCostRepository(p.conn).get_by_order(oid).id


def test_changing_the_costing_method_changes_the_cost_without_touching_processing(lomo):
    """El método es configuración de Costos. Procesamiento ejecuta igual."""
    p, entero, chuleta, recorte = lomo
    p.conn.execute("INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES (?,?)",
                   ("costing.processing.allocation_method", "WEIGHT_BASED"))
    p.conn.commit()
    oid = p.lista(ProcessType.CUTTING, entero, "10")
    assert p.ejecutar(oid, {chuleta: "7", recorte: "3"}).success
    lineas = {l.product_id: l for l in ProcessingCostRepository(p.conn).get_by_order(oid).lines
              if l.line_kind == "OUTPUT"}
    assert lineas[chuleta].unit_cost == lineas[recorte].unit_cost == Decimal("80.0000")


def test_without_input_cost_nothing_is_consumed_and_no_cost_is_invented(lomo):
    p, entero, chuleta, recorte = lomo
    p.conn.execute("DELETE FROM product_cost")
    p.conn.commit()
    oid = p.lista(ProcessType.CUTTING, entero, "10")
    r = p.ejecutar(oid, {chuleta: "7", recorte: "3"})
    assert not r.success and r.error_code == "MISSING_INPUT_COST"
    assert p.saldo(entero) == Decimal("50") and p.saldo(chuleta) == Decimal("0")
    assert ProcessingCostRepository(p.conn).get_by_order(oid) is None


def test_the_inventory_strategy_setting_is_unrelated_to_cost(lomo):
    """Sanidad: configurar la asignación de lotes (Inventario) no mueve costos."""
    p, entero, chuleta, recorte = lomo
    InventorySettingsRepository(p.conn).set(setting_key="production.allocation_strategy",
                                            setting_value="FIFO")
    p.conn.commit()
    oid = p.lista(ProcessType.CUTTING, entero, "10")
    assert p.ejecutar(oid, {chuleta: "7", recorte: "3"}).success
    asignacion = ProcessingCostRepository(p.conn).get_by_order(oid)
    assert asignacion.method == "RELATIVE_SALES_VALUE"
    assert asignacion.input_cost_total == Decimal("800.00")
