# tests/test_financial_core_phase2.py — Phase 2 financial core regression tests
"""
Regression tests for Phase 2 financial core enforcement changes:

1. ComisionesService GL accrual (devengamiento + pago)
2. ProductionFinanceHandler GL entries (raw material + finished goods)
3. finance_service.sync_cxp_from_compras SAVEPOINT atomicity
4. finance_service.sync_cxc_from_ventas SAVEPOINT atomicity
5. finanzas_unificadas CxC fallback removal (no direct INSERT)
"""
from __future__ import annotations
import sqlite3
import unittest
from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TrackedFinance:
    """Records registrar_asiento calls for assertion."""
    def __init__(self):
        self.calls = []

    def registrar_asiento(self, **kwargs):
        self.calls.append(kwargs)

    def last(self):
        return self.calls[-1] if self.calls else None


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS comisiones_config (
            usuario TEXT PRIMARY KEY,
            pct_comision REAL,
            activo INTEGER,
            sucursal_id INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS comisiones_acumuladas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            venta_id INTEGER,
            total_venta REAL,
            pct REAL,
            monto REAL,
            sucursal_id INTEGER DEFAULT 1,
            turno_fecha TEXT DEFAULT (date('now')),
            pagado INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# 1. ComisionesService GL accrual
# ---------------------------------------------------------------------------

class TestComisionesServiceGL(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from core.services.comisiones_service import ComisionesService
        self.db = _make_db()
        self.finance = TrackedFinance()
        self.svc = ComisionesService(db_conn=self.db, finance_service=self.finance)

    def _set_config(self, usuario, pct):
        self.db.execute(
            "INSERT INTO comisiones_config(usuario, pct_comision, activo, sucursal_id) VALUES (?,?,1,1)",
            (usuario, pct),
        )
        self.db.commit()

    def test_accrual_posts_debe_gasto_haber_pasivo(self):
        """Devengamiento posts 6103-comisiones-por-venta / 2301-comisiones-por-pagar."""
        self._set_config("cajero1", 5.0)
        self.svc.registrar_comision("cajero1", venta_id=101, total_venta=1000.0, sucursal_id=1)

        self.assertEqual(len(self.finance.calls), 1)
        entry = self.finance.calls[0]
        self.assertEqual(entry["debe"], "6103-comisiones-por-venta")
        self.assertEqual(entry["haber"], "2301-comisiones-por-pagar")
        self.assertAlmostEqual(entry["monto"], 50.0)
        self.assertEqual(entry["evento"], "COMISION_DEVENGADA")

    def test_accrual_amount_matches_percentage(self):
        """Commission amount = total_venta * pct / 100."""
        self._set_config("cajero2", 3.5)
        monto = self.svc.registrar_comision("cajero2", venta_id=202, total_venta=2000.0)
        self.assertAlmostEqual(monto, 70.0)

    def test_no_asiento_when_not_active(self):
        """No GL entry when commission config is inactive."""
        self.db.execute(
            "INSERT INTO comisiones_config(usuario, pct_comision, activo) VALUES ('inactivo', 5.0, 0)"
        )
        self.db.commit()
        self.svc.registrar_comision("inactivo", venta_id=303, total_venta=500.0)
        self.assertEqual(len(self.finance.calls), 0)

    def test_no_asiento_when_no_config(self):
        """No GL entry when user has no commission config."""
        self.svc.registrar_comision("noconfig", venta_id=404, total_venta=500.0)
        self.assertEqual(len(self.finance.calls), 0)

    def test_payment_posts_pasivo_debe_caja_haber(self):
        """marcar_pagadas posts 2301-comisiones-por-pagar / 110-caja."""
        self._set_config("cajero3", 2.0)
        self.svc.registrar_comision("cajero3", venta_id=505, total_venta=500.0)
        # Clear accrual entry
        self.finance.calls.clear()

        self.svc.marcar_pagadas("cajero3", "2026-01-01", "2026-12-31", sucursal_id=1)

        self.assertEqual(len(self.finance.calls), 1)
        entry = self.finance.calls[0]
        self.assertEqual(entry["debe"], "2301-comisiones-por-pagar")
        self.assertEqual(entry["haber"], "110-caja")
        self.assertEqual(entry["evento"], "COMISION_PAGADA")
        self.assertAlmostEqual(entry["monto"], 10.0)  # 500 * 2% = 10

    def test_no_finance_service_safe(self):
        """ComisionesService works without finance_service (no-op GL)."""
        from core.services.comisiones_service import ComisionesService
        svc = ComisionesService(db_conn=self.db, finance_service=None)
        self._set_config("cajero4", 1.0)
        # Should not raise
        monto = svc.registrar_comision("cajero4", venta_id=606, total_venta=100.0)
        self.assertAlmostEqual(monto, 1.0)


# ---------------------------------------------------------------------------
# 2. ProductionFinanceHandler GL entries
# ---------------------------------------------------------------------------

class TestProductionFinanceHandler(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from core.events.handlers.production_handler import ProductionFinanceHandler
        self.finance = TrackedFinance()
        self.handler = ProductionFinanceHandler(finance_service=self.finance)

    def _payload(self, raw=100.0, finished=80.0, batch_id="BATCH-001"):
        return {
            "batch_id": batch_id,
            "folio": "F-001",
            "sucursal_id": 1,
            "rendimiento_pct": 80.0,
            "cost_allocations": {
                "raw_material_cost": raw,
                "finished_goods_cost": finished,
            },
        }

    def test_raw_material_posts_correct_accounts(self):
        """Raw material cost: debe=7001-costo-materia-prima / haber=1201-inventario-mp."""
        self.handler.handle(self._payload(raw=100.0, finished=0.0))
        self.assertEqual(len(self.finance.calls), 1)
        entry = self.finance.calls[0]
        self.assertEqual(entry["debe"], "7001-costo-materia-prima-consumida")
        self.assertEqual(entry["haber"], "1201-inventario-materia-prima")
        self.assertAlmostEqual(entry["monto"], 100.0)
        self.assertEqual(entry["evento"], "PRODUCCION_COMPLETADA")

    def test_finished_goods_posts_correct_accounts(self):
        """Finished goods: debe=1202-inventario-pt / haber=7002-costo-produccion."""
        self.handler.handle(self._payload(raw=0.0, finished=80.0))
        self.assertEqual(len(self.finance.calls), 1)
        entry = self.finance.calls[0]
        self.assertEqual(entry["debe"], "1202-inventario-productos-terminados")
        self.assertEqual(entry["haber"], "7002-costo-produccion-valor-agregado")
        self.assertAlmostEqual(entry["monto"], 80.0)

    def test_both_costs_post_two_entries(self):
        """Both raw and finished costs each produce one GL entry."""
        self.handler.handle(self._payload(raw=100.0, finished=80.0))
        self.assertEqual(len(self.finance.calls), 2)
        debits = {c["debe"] for c in self.finance.calls}
        self.assertIn("7001-costo-materia-prima-consumida", debits)
        self.assertIn("1202-inventario-productos-terminados", debits)

    def test_zero_costs_no_entries(self):
        """Zero cost_allocations with no movimientos produces no GL entries."""
        self.handler.handle({
            "batch_id": "B0",
            "sucursal_id": 1,
            "cost_allocations": {"raw_material_cost": 0, "finished_goods_cost": 0},
        })
        self.assertEqual(len(self.finance.calls), 0)

    def test_finance_error_does_not_reraise(self):
        """Post-commit handler: finance errors are logged, not re-raised."""
        bad_finance = MagicMock()
        bad_finance.registrar_asiento.side_effect = RuntimeError("GL down")
        from core.events.handlers.production_handler import ProductionFinanceHandler
        handler = ProductionFinanceHandler(finance_service=bad_finance)
        # Must not raise
        handler.handle(self._payload(raw=50.0, finished=40.0))

    def test_no_finance_service_is_noop(self):
        """Handler with finance_service=None is a safe no-op."""
        from core.events.handlers.production_handler import ProductionFinanceHandler
        handler = ProductionFinanceHandler(finance_service=None)
        handler.handle(self._payload())  # must not raise


# ---------------------------------------------------------------------------
# 3. sync_cxp_from_compras SAVEPOINT atomicity (static analysis)
# ---------------------------------------------------------------------------

class TestSyncSavepointStaticAnalysis(unittest.TestCase):
    """
    Verifies that sync_cxp_from_compras and sync_cxc_from_ventas use
    SAVEPOINT for atomicity. We check this at the source level since
    spinning up the full FinanceService requires the whole DB schema.
    """

    def _get_method_source(self, method_name):
        import os, ast, textwrap, inspect

        src_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "core", "services", "enterprise", "finance_service.py",
        )
        with open(src_path) as f:
            source = f.read()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        lines = source.splitlines()
                        start = item.lineno - 1
                        end = item.end_lineno
                        return "\n".join(lines[start:end])
        return ""

    def test_sync_cxp_uses_savepoint(self):
        """sync_cxp_from_compras must use SAVEPOINT for transactional safety."""
        src = self._get_method_source("sync_cxp_from_compras")
        self.assertIn("SAVEPOINT", src,
                      "sync_cxp_from_compras must wrap loop in a SAVEPOINT")

    def test_sync_cxp_releases_or_rolls_back_savepoint(self):
        """sync_cxp_from_compras must RELEASE or ROLLBACK the SAVEPOINT."""
        src = self._get_method_source("sync_cxp_from_compras")
        has_release = "RELEASE SAVEPOINT" in src
        has_rollback = "ROLLBACK TO SAVEPOINT" in src
        self.assertTrue(has_release or has_rollback,
                        "sync_cxp_from_compras must RELEASE or ROLLBACK SAVEPOINT")

    def test_sync_cxc_uses_savepoint(self):
        """sync_cxc_from_ventas must use SAVEPOINT for transactional safety."""
        src = self._get_method_source("sync_cxc_from_ventas")
        self.assertIn("SAVEPOINT", src,
                      "sync_cxc_from_ventas must wrap loop in a SAVEPOINT")


# ---------------------------------------------------------------------------
# 4. finanzas_unificadas CxC section: no direct INSERT fallback
# ---------------------------------------------------------------------------

class TestFinanzasUnificadasNoCxcFallback(unittest.TestCase):
    """
    Verifies that the CxC creation path in finanzas_unificadas.py does NOT
    contain any raw SQL INSERT fallback into accounts_receivable.

    This is a static analysis test — we parse the source and check that
    the INSERT INTO accounts_receivable pattern only appears in legitimate
    service methods, not as a UI fallback.
    """

    def test_no_bare_insert_into_accounts_receivable_in_ui_module(self):
        import os, ast

        src_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "modulos",
            "finanzas_unificadas.py",
        )
        with open(src_path) as f:
            source = f.read()

        tree = ast.parse(source)

        # Find all class method bodies that contain "accounts_receivable" INSERT
        # We expect ZERO direct INSERT calls in class FinanzasUnificadas
        dangerous_pattern = "INSERT INTO accounts_receivable"
        if dangerous_pattern in source:
            # Find which methods contain it
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and "Finanza" in node.name:
                    for item in ast.walk(node):
                        if isinstance(item, (ast.Constant, ast.Str)):
                            val = item.s if isinstance(item, ast.Str) else item.value
                            if isinstance(val, str) and "INSERT INTO accounts_receivable" in val:
                                self.fail(
                                    f"Direct INSERT INTO accounts_receivable found in "
                                    f"FinanzasUnificadas class — raw SQL fallback must be removed."
                                )

    def test_cxc_creation_requires_finance_service(self):
        """Source code must guard for FinanceService availability before crear_cxc."""
        import os

        src_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "modulos",
            "finanzas_unificadas.py",
        )
        with open(src_path) as f:
            source = f.read()

        # The guard must appear: check for finance service existence before crear_cxc
        self.assertIn("not hasattr(self._fs, \"crear_cxc\")", source,
                      "CxC creation must guard for FinanceService.crear_cxc availability")


if __name__ == "__main__":
    unittest.main(verbosity=2)
