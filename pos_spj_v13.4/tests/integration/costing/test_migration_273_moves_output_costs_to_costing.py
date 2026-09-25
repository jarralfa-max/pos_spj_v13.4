"""Migración 273: el costo por salida que la Fase 10 guardaba en Procesamiento
pasa a Costos sin perder historia, y la tabla de resultados queda sin columnas
de costo (antes guardaba un '0' inventado en cada fila nueva)."""
from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal

from backend.infrastructure.db.repositories.costing.processing_cost_repository import (
    ProcessingCostRepository,
)
from backend.shared.ids import new_uuid

#: `processing_output_results` tal como la dejó la migración 270 (Fase 10).
_TABLA_FASE_10 = """
    CREATE TABLE processing_output_results (
        id TEXT NOT NULL PRIMARY KEY,
        processing_order_id TEXT NOT NULL REFERENCES processing_orders(id),
        product_id TEXT NOT NULL, output_type TEXT NOT NULL, input_product_id TEXT NOT NULL,
        input_weight TEXT NOT NULL, input_unit_cost TEXT NOT NULL DEFAULT '0',
        expected_weight TEXT NOT NULL DEFAULT '0', actual_weight TEXT NOT NULL DEFAULT '0',
        difference_weight TEXT NOT NULL DEFAULT '0',
        expected_yield_pct TEXT NOT NULL DEFAULT '0', yield_pct TEXT NOT NULL DEFAULT '0',
        variance_pct TEXT, unit_price TEXT, allocated_cost TEXT NOT NULL DEFAULT '0',
        unit_cost TEXT NOT NULL DEFAULT '0', input_lot_id TEXT, output_lot_id TEXT,
        created_at TEXT NOT NULL, UNIQUE (processing_order_id, product_id))
"""


def _db():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE processing_orders (id TEXT PRIMARY KEY, branch_id TEXT,"
              " process_type TEXT, created_by_user_id TEXT, closed_by_user_id TEXT)")
    c.execute(_TABLA_FASE_10)
    return c


def _orden_costeada(c):
    orden, entrada, cerrada_por = new_uuid(), new_uuid(), new_uuid()
    c.execute("INSERT INTO processing_orders VALUES (?,?,?,?,?)",
              (orden, new_uuid(), "CUTTING", new_uuid(), cerrada_por))
    for producto, tipo, peso, precio, costo, unitario in (
            (new_uuid(), "MAIN_PRODUCT", "3.4", "120", "283.33", "83.3324"),
            (new_uuid(), "CO_PRODUCT", "3.0", "80", "216.67", "72.2233"),
            (new_uuid(), "WASTE", "0.5", None, "0", "0")):
        c.execute("INSERT INTO processing_output_results (id, processing_order_id, product_id,"
                  " output_type, input_product_id, input_weight, input_unit_cost, actual_weight,"
                  " unit_price, allocated_cost, unit_cost, created_at)"
                  " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (new_uuid(), orden, producto, tipo, entrada, "10", "50", peso, precio, costo,
                   unitario, "2026-09-21T10:00:00+00:00"))
    c.commit()
    return orden, entrada, cerrada_por


def _migrar(c):
    importlib.import_module("migrations.standalone.273_costing_and_quality_contexts").run(c)


def test_the_cost_history_moves_to_costing_without_losing_a_cent():
    c = _db()
    orden, entrada, cerrada_por = _orden_costeada(c)
    _migrar(c)

    asignacion = ProcessingCostRepository(c).get_by_order(orden)
    assert asignacion is not None
    assert asignacion.method == "RELATIVE_SALES_VALUE"
    assert asignacion.input_cost_total == Decimal("500.00")
    assert asignacion.created_by_user_id == cerrada_por
    salidas = [l for l in asignacion.lines if l.line_kind == "OUTPUT"]
    assert sum(l.allocated_cost for l in salidas) == Decimal("500.00")
    [insumo] = [l for l in asignacion.lines if l.line_kind == "INPUT"]
    assert (insumo.product_id, insumo.unit_cost) == (entrada, Decimal("50"))


def test_the_results_table_keeps_every_row_and_loses_only_the_cost_columns():
    c = _db()
    orden, _, _ = _orden_costeada(c)
    _migrar(c)

    columnas = {r[1] for r in c.execute("PRAGMA table_info(processing_output_results)")}
    assert not columnas & {"input_unit_cost", "unit_price", "allocated_cost", "unit_cost"}
    assert c.execute("SELECT COUNT(*) FROM processing_output_results WHERE"
                     " processing_order_id=?", (orden,)).fetchone()[0] == 3
    assert c.execute("SELECT actual_weight FROM processing_output_results WHERE"
                     " output_type='MAIN_PRODUCT'").fetchone()[0] == "3.4"


def test_it_is_idempotent_and_emits_no_events():
    c = _db()
    orden, _, _ = _orden_costeada(c)
    _migrar(c)
    _migrar(c)
    assert c.execute("SELECT COUNT(*) FROM processing_cost_allocations").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM costing_outbox").fetchone()[0] == 0
