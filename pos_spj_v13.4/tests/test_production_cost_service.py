"""
tests/test_production_cost_service.py — FASE 6

Verifica que ProductionCostService:
  - compute_batch_costs: lee production_batches + production_cost_ledger +
    production_outputs y devuelve sumas correctas de raw/finished/waste
  - update_average_costs: actualiza costo en productos e inventario_actual
    solo para outputs no-merma
  - Lanza ValueError cuando batch_id no existe
  - ProductionFinanceHandler: llama registrar_asiento con montos reales
    cuando db= está disponible
  - ProductionFinanceHandler: fallback a payload dict cuando db=None
  - ProductionFinanceHandler: silencioso cuando no hay datos de costo
"""
from __future__ import annotations

import sqlite3
import sys
import os
import pytest
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.finance.production_cost_service import (
    ProductionCostService,
    ProductionCostSummary,
    OutputCostLine,
)
from core.events.handlers.production_handler import ProductionFinanceHandler


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE productos (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre  TEXT,
            costo   REAL DEFAULT 0
        );
        CREATE TABLE sucursales (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT
        );
        CREATE TABLE inventario_actual (
            producto_id   INTEGER,
            sucursal_id   INTEGER,
            cantidad      REAL DEFAULT 0,
            costo_promedio REAL DEFAULT 0,
            UNIQUE(producto_id, sucursal_id)
        );
        CREATE TABLE production_batches (
            id                TEXT PRIMARY KEY,
            product_source_id INTEGER,
            source_weight     REAL DEFAULT 0,
            source_cost_total REAL DEFAULT 0,
            branch_id         INTEGER DEFAULT 1,
            estado            TEXT DEFAULT 'cerrado'
        );
        CREATE TABLE production_outputs (
            id         TEXT PRIMARY KEY,
            batch_id   TEXT,
            product_id INTEGER,
            weight     REAL DEFAULT 0,
            is_waste   INTEGER DEFAULT 0
        );
        CREATE TABLE production_cost_ledger (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id    TEXT,
            output_id   TEXT,
            product_id  INTEGER,
            weight      REAL,
            pct_utilizable REAL DEFAULT 0,
            cost_total  REAL,
            cost_per_kg REAL
        );
    """)
    # Seed: 1 raw source, 3 output products (2 finished + 1 waste)
    conn.executescript("""
        INSERT INTO productos (nombre, costo) VALUES
            ('Pollo Entero', 50.0),  -- id=1 source
            ('Pechuga',       0.0),  -- id=2 finished
            ('Pierna',        0.0),  -- id=3 finished
            ('Merma',         0.0);  -- id=4 waste
        INSERT INTO sucursales (nombre) VALUES ('Central');
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad, costo_promedio)
        VALUES (2, 1, 5.0, 0.0), (3, 1, 3.0, 0.0), (4, 1, 1.0, 0.0);
    """)
    conn.commit()
    yield conn
    conn.close()


def _seed_batch(db, batch_id="B001", raw_cost=1000.0, branch_id=1):
    """Insert a closed production batch with outputs and cost ledger."""
    db.execute(
        "INSERT INTO production_batches VALUES (?, 1, 20.0, ?, ?, 'cerrado')",
        (batch_id, raw_cost, branch_id),
    )
    # Outputs: 12 kg pechuga (finished), 7 kg pierna (finished), 1 kg merma (waste)
    db.execute("INSERT INTO production_outputs VALUES ('O1', ?, 2, 12.0, 0)", (batch_id,))
    db.execute("INSERT INTO production_outputs VALUES ('O2', ?, 3,  7.0, 0)", (batch_id,))
    db.execute("INSERT INTO production_outputs VALUES ('O3', ?, 4,  1.0, 1)", (batch_id,))  # waste

    # Cost ledger: total 1000 split 60/35/5
    db.execute(
        "INSERT INTO production_cost_ledger (batch_id, output_id, product_id, weight, cost_total, cost_per_kg) "
        "VALUES (?, 'O1', 2, 12.0, 600.0, 50.0)",
        (batch_id,),
    )
    db.execute(
        "INSERT INTO production_cost_ledger (batch_id, output_id, product_id, weight, cost_total, cost_per_kg) "
        "VALUES (?, 'O2', 3, 7.0, 350.0, 50.0)",
        (batch_id,),
    )
    db.execute(
        "INSERT INTO production_cost_ledger (batch_id, output_id, product_id, weight, cost_total, cost_per_kg) "
        "VALUES (?, 'O3', 4, 1.0, 50.0, 50.0)",
        (batch_id,),
    )
    db.commit()


# ── ProductionCostService.compute_batch_costs ─────────────────────────────────

class TestComputeBatchCosts:

    def test_returns_summary_with_correct_totals(self, db):
        _seed_batch(db)
        svc = ProductionCostService(db)
        s = svc.compute_batch_costs("B001")

        assert isinstance(s, ProductionCostSummary)
        assert s.batch_id == "B001"
        assert abs(s.raw_material_cost - 1000.0) < 0.001
        assert abs(s.finished_goods_cost - 950.0) < 0.001  # 600 + 350
        assert abs(s.waste_cost - 50.0) < 0.001

    def test_output_costs_list_length(self, db):
        _seed_batch(db)
        s = ProductionCostService(db).compute_batch_costs("B001")
        assert len(s.output_costs) == 3

    def test_is_waste_flag_correct(self, db):
        _seed_batch(db)
        s = ProductionCostService(db).compute_batch_costs("B001")
        waste_lines = [l for l in s.output_costs if l.is_waste]
        finished_lines = [l for l in s.output_costs if not l.is_waste]
        assert len(waste_lines) == 1
        assert waste_lines[0].product_id == 4  # Merma
        assert len(finished_lines) == 2

    def test_branch_id_from_batch(self, db):
        _seed_batch(db, branch_id=3)
        s = ProductionCostService(db).compute_batch_costs("B001")
        assert s.branch_id == 3

    def test_source_product_id_from_batch(self, db):
        _seed_batch(db)
        s = ProductionCostService(db).compute_batch_costs("B001")
        assert s.source_product_id == 1  # Pollo Entero

    def test_empty_cost_ledger_returns_zero_costs(self, db):
        db.execute(
            "INSERT INTO production_batches VALUES ('B002', 1, 10.0, 500.0, 1, 'cerrado')"
        )
        db.commit()
        s = ProductionCostService(db).compute_batch_costs("B002")
        assert s.raw_material_cost == 500.0
        assert s.finished_goods_cost == 0.0
        assert s.waste_cost == 0.0
        assert s.output_costs == []

    def test_missing_batch_raises_value_error(self, db):
        with pytest.raises(ValueError, match="not found"):
            ProductionCostService(db).compute_batch_costs("NOPE")

    def test_zero_raw_cost_batch(self, db):
        _seed_batch(db, batch_id="B003", raw_cost=0.0)
        s = ProductionCostService(db).compute_batch_costs("B003")
        assert s.raw_material_cost == 0.0
        # cost ledger still has values
        assert s.finished_goods_cost > 0


# ── ProductionCostService.update_average_costs ────────────────────────────────

class TestUpdateAverageCosts:

    def test_updates_productos_costo_for_finished_outputs(self, db):
        _seed_batch(db)
        ProductionCostService(db).update_average_costs("B001")
        pechuga = db.execute("SELECT costo FROM productos WHERE id=2").fetchone()[0]
        pierna  = db.execute("SELECT costo FROM productos WHERE id=3").fetchone()[0]
        assert abs(pechuga - 50.0) < 0.001
        assert abs(pierna - 50.0) < 0.001

    def test_updates_inventario_actual_costo_promedio(self, db):
        _seed_batch(db)
        ProductionCostService(db).update_average_costs("B001")
        p = db.execute(
            "SELECT costo_promedio FROM inventario_actual WHERE producto_id=2"
        ).fetchone()[0]
        assert abs(p - 50.0) < 0.001

    def test_does_not_update_waste_products(self, db):
        _seed_batch(db)
        ProductionCostService(db).update_average_costs("B001")
        merma_costo = db.execute("SELECT costo FROM productos WHERE id=4").fetchone()[0]
        assert merma_costo == 0.0  # waste product unchanged

    def test_returns_count_of_updated_products(self, db):
        _seed_batch(db)
        n = ProductionCostService(db).update_average_costs("B001")
        assert n == 2  # pechuga + pierna (not waste)

    def test_no_ledger_rows_returns_zero(self, db):
        db.execute(
            "INSERT INTO production_batches VALUES ('B002', 1, 0.0, 0.0, 1, 'cerrado')"
        )
        db.commit()
        n = ProductionCostService(db).update_average_costs("B002")
        assert n == 0

    def test_zero_cost_per_kg_skipped(self, db):
        """Rows with cost_per_kg=0 must not overwrite existing costs."""
        db.execute(
            "INSERT INTO production_batches VALUES ('B003', 1, 1.0, 0.0, 1, 'cerrado')"
        )
        db.execute("INSERT INTO production_outputs VALUES ('O9', 'B003', 2, 1.0, 0)")
        db.execute(
            "INSERT INTO production_cost_ledger (batch_id, output_id, product_id, weight, cost_total, cost_per_kg) "
            "VALUES ('B003', 'O9', 2, 1.0, 0.0, 0.0)"
        )
        db.execute("UPDATE productos SET costo=99.0 WHERE id=2")
        db.commit()
        ProductionCostService(db).update_average_costs("B003")
        costo = db.execute("SELECT costo FROM productos WHERE id=2").fetchone()[0]
        assert abs(costo - 99.0) < 0.001  # not overwritten


# ── ProductionFinanceHandler ──────────────────────────────────────────────────

class TestProductionFinanceHandler:

    def _make_finance(self):
        m = MagicMock()
        m.registrar_asiento = MagicMock()
        return m

    def _payload(self, batch_id="B001", folio="LT-001", sucursal_id=1):
        return {
            "batch_id":         batch_id,
            "folio":            folio,
            "sucursal_id":      sucursal_id,
            "rendimiento_pct":  80.0,
            "cost_allocations": 3,   # old integer format — should be ignored
        }

    def test_queries_cost_service_when_db_provided(self, db):
        _seed_batch(db)
        fin = self._make_finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=db)
        handler.handle(self._payload())
        assert fin.registrar_asiento.call_count >= 2  # raw + finished at minimum

    def test_raw_material_gl_entry_posted_with_correct_amount(self, db):
        _seed_batch(db)
        fin = self._make_finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=db)
        handler.handle(self._payload())
        calls_by_debe = {c[1]["debe"]: c[1]["monto"] for c in fin.registrar_asiento.call_args_list}
        assert "7001-costo-materia-prima-consumida" in calls_by_debe
        assert abs(calls_by_debe["7001-costo-materia-prima-consumida"] - 1000.0) < 0.001

    def test_finished_goods_gl_entry_posted(self, db):
        _seed_batch(db)
        fin = self._make_finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=db)
        handler.handle(self._payload())
        calls_by_debe = {c[1]["debe"]: c[1]["monto"] for c in fin.registrar_asiento.call_args_list}
        assert "1202-inventario-productos-terminados" in calls_by_debe
        assert abs(calls_by_debe["1202-inventario-productos-terminados"] - 950.0) < 0.001

    def test_waste_gl_entry_posted(self, db):
        _seed_batch(db)
        fin = self._make_finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=db)
        handler.handle(self._payload())
        calls_by_debe = {c[1]["debe"]: c[1]["monto"] for c in fin.registrar_asiento.call_args_list}
        assert "7003-costo-merma-produccion" in calls_by_debe
        assert abs(calls_by_debe["7003-costo-merma-produccion"] - 50.0) < 0.001

    def test_handler_also_updates_costo_promedio(self, db):
        _seed_batch(db)
        fin = self._make_finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=db)
        handler.handle(self._payload())
        pechuga = db.execute("SELECT costo FROM productos WHERE id=2").fetchone()[0]
        assert abs(pechuga - 50.0) < 0.001

    def test_no_db_uses_dict_payload_fallback(self):
        fin = self._make_finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=None)
        handler.handle({
            "batch_id": "B999",
            "folio": "LT-999",
            "sucursal_id": 1,
            "cost_allocations": {
                "raw_material_cost": 200.0,
                "finished_goods_cost": 180.0,
            },
        })
        calls_by_debe = {c[1]["debe"]: c[1]["monto"] for c in fin.registrar_asiento.call_args_list}
        assert abs(calls_by_debe.get("7001-costo-materia-prima-consumida", 0) - 200.0) < 0.001
        assert abs(calls_by_debe.get("1202-inventario-productos-terminados", 0) - 180.0) < 0.001

    def test_no_cost_data_is_silent(self):
        fin = self._make_finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=None)
        handler.handle({
            "batch_id": "B999",
            "folio": "LT-999",
            "sucursal_id": 1,
            "cost_allocations": 3,  # integer — not a dict
        })
        fin.registrar_asiento.assert_not_called()

    def test_no_finance_service_is_noop(self, db):
        _seed_batch(db)
        handler = ProductionFinanceHandler(finance_service=None, db=db)
        handler.handle(self._payload())  # must not raise

    def test_missing_finance_service_attr_is_noop(self, db):
        _seed_batch(db)
        fin = object()  # no registrar_asiento attr
        handler = ProductionFinanceHandler(finance_service=fin, db=db)
        handler.handle(self._payload())  # must not raise

    def test_bad_batch_id_logs_warning_does_not_raise(self):
        fin = self._make_finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=sqlite3.connect(":memory:"))
        handler.handle({"batch_id": "NONEXISTENT", "folio": "X", "sucursal_id": 1})
        fin.registrar_asiento.assert_not_called()
