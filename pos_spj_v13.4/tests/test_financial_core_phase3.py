# tests/test_financial_core_phase3.py — Phase 3 financial core regression tests
"""
Regression tests for Phase 3 financial core enforcement:

1. LoyaltyService.acreditar_venta — GL accrual (6201/215.1) when points are earned
2. TreasuryService.registrar_gasto_opex — GL entry (6102/110-caja or 112-banco)
3. Asset maintenance GL flows through treasury opex GL
"""
from __future__ import annotations
import sqlite3
import unittest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TrackedFinance:
    def __init__(self):
        self.calls = []

    def registrar_asiento(self, **kwargs):
        self.calls.append(kwargs)

    def last(self):
        return self.calls[-1] if self.calls else None


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# 1. LoyaltyService GL accrual on point accrual
# ---------------------------------------------------------------------------

class TestLoyaltyAccrualGL(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        self.finance = TrackedFinance()

    def _make_svc(self, puntos=10):
        """Build a LoyaltyService with a stubbed engine that returns `puntos` earned."""
        from core.services.loyalty_service import LoyaltyService

        db = _make_db()
        svc = LoyaltyService.__new__(LoyaltyService)
        svc.db = db
        svc.sucursal_id = 1
        svc._module_config = None  # enabled property returns True when None
        svc._finance = self.finance
        svc._bus = None

        # Stub _ensure_tables, _init_bus, _init_engine (all noop for unit test)
        svc._ensure_tables = lambda: None
        svc._registrar_pasivo = lambda *a, **k: None
        svc._publish_puntos = lambda *a, **k: None
        svc.registrar_en_ledger = lambda **k: None
        svc._get_cajero_id = lambda u: 1

        # Stub _cfg to return a known star value
        svc._cfg = lambda key, default="": "0.10" if "valor_estrella" in key else default

        # Stub GrowthEngine with fixed result
        engine = MagicMock()
        engine.procesar_venta.return_value = {
            "estrellas_ganadas": puntos,
            "saldo_actual": puntos,
        }
        svc._engine = engine
        return svc

    def test_accrual_posts_gasto_debe_pasivo_haber(self):
        """Points earned → debe=6201-descuentos-fidelizacion, haber=215.1-pasivo-fidelizacion."""
        svc = self._make_svc(puntos=10)
        svc.acreditar_venta(cliente_id=1, venta_id=101, cajero="cajero", total=100.0)

        self.assertEqual(len(self.finance.calls), 1)
        entry = self.finance.calls[0]
        self.assertEqual(entry["debe"], "6201-descuentos-fidelizacion")
        self.assertEqual(entry["haber"], "215.1-pasivo-fidelizacion")
        self.assertAlmostEqual(entry["monto"], 1.0)  # 10 pts × $0.10
        self.assertEqual(entry["evento"], "PUNTOS_ACREDITADOS")

    def test_accrual_amount_scales_with_points(self):
        """GL monto = estrellas × valor_estrella."""
        svc = self._make_svc(puntos=50)
        svc.acreditar_venta(cliente_id=2, venta_id=202, cajero="cajero", total=500.0)
        self.assertAlmostEqual(self.finance.calls[0]["monto"], 5.0)  # 50 × 0.10

    def test_no_gl_when_zero_points(self):
        """No GL entry when no points are awarded."""
        svc = self._make_svc(puntos=0)
        svc.acreditar_venta(cliente_id=3, venta_id=303, cajero="cajero", total=10.0)
        self.assertEqual(len(self.finance.calls), 0)

    def test_no_gl_when_no_finance_service(self):
        """No GL entry and no crash when finance_service is None."""
        svc = self._make_svc(puntos=5)
        svc._finance = None
        svc.acreditar_venta(cliente_id=4, venta_id=404, cajero="cajero", total=50.0)
        # Must not raise; finance.calls not applicable here

    def test_gl_failure_does_not_propagate(self):
        """GL error during accrual is logged but does not abort the loyalty flow."""
        svc = self._make_svc(puntos=5)
        self.finance.registrar_asiento = MagicMock(side_effect=RuntimeError("GL down"))
        result = svc.acreditar_venta(cliente_id=5, venta_id=505, cajero="cajero", total=50.0)
        # The loyalty result should still be returned
        self.assertEqual(result.get("estrellas_ganadas"), 5)


# ---------------------------------------------------------------------------
# 2. TreasuryService GL on registrar_gasto_opex
# ---------------------------------------------------------------------------

class TestTreasuryGastoOpexGL(unittest.TestCase):

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        self.finance = TrackedFinance()
        self.db = _make_db()
        # Create the minimal tables treasury needs
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS treasury_ledger (
                id TEXT PRIMARY KEY,
                fecha TEXT DEFAULT (datetime('now')),
                tipo TEXT NOT NULL,
                categoria TEXT NOT NULL,
                concepto TEXT DEFAULT '',
                ingreso REAL DEFAULT 0,
                egreso REAL DEFAULT 0,
                sucursal_id INTEGER DEFAULT 0,
                referencia TEXT DEFAULT '',
                usuario TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS gastos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                categoria TEXT,
                concepto TEXT,
                monto REAL,
                metodo_pago TEXT,
                usuario TEXT,
                fecha_registro TEXT
            );
        """)
        self.db.commit()

    def _make_svc(self):
        from core.services.finance.treasury_service import TreasuryService
        svc = TreasuryService.__new__(TreasuryService)
        svc.db = self.db
        svc._module_config = None
        svc._finance = self.finance
        svc._bus = None
        svc._ensure_tables = lambda: None
        return svc

    def test_efectivo_posts_caja_haber(self):
        """Efectivo opex: debe=6102-gastos-operativos, haber=110-caja."""
        svc = self._make_svc()
        svc.registrar_gasto_opex(
            categoria="Limpieza", concepto="Compra escobas",
            monto=200.0, metodo_pago="efectivo", sucursal_id=1,
        )
        entry = self.finance.last()
        self.assertIsNotNone(entry)
        self.assertEqual(entry["debe"], "6102-gastos-operativos")
        self.assertEqual(entry["haber"], "110-caja")
        self.assertAlmostEqual(entry["monto"], 200.0)
        self.assertEqual(entry["evento"], "GASTO_OPEX")

    def test_transferencia_posts_banco_haber(self):
        """Transferencia opex: haber=112-banco."""
        svc = self._make_svc()
        svc.registrar_gasto_opex(
            categoria="Renta", concepto="Renta local",
            monto=5000.0, metodo_pago="transferencia", sucursal_id=1,
        )
        entry = self.finance.last()
        self.assertEqual(entry["haber"], "112-banco")

    def test_tarjeta_posts_banco_haber(self):
        """Tarjeta payment maps to banco (not caja)."""
        svc = self._make_svc()
        svc.registrar_gasto_opex(
            categoria="Papelería", concepto="Compra papel",
            monto=150.0, metodo_pago="tarjeta", sucursal_id=1,
        )
        self.assertEqual(self.finance.last()["haber"], "112-banco")

    def test_no_gl_when_monto_zero(self):
        """Zero-amount opex does not generate a GL entry."""
        svc = self._make_svc()
        svc.registrar_gasto_opex(categoria="X", concepto="Y", monto=0)
        self.assertEqual(len(self.finance.calls), 0)

    def test_no_finance_service_does_not_crash(self):
        """TreasuryService works without finance_service."""
        svc = self._make_svc()
        svc._finance = None
        svc.registrar_gasto_opex(
            categoria="Luz", concepto="CFE mes", monto=800.0, sucursal_id=1,
        )
        # No GL calls, no crash
        self.assertEqual(len(self.finance.calls), 0)

    def test_finance_error_does_not_propagate(self):
        """GL failure is logged but opex record is still written."""
        svc = self._make_svc()
        self.finance.registrar_asiento = MagicMock(side_effect=RuntimeError("GL fail"))
        svc.registrar_gasto_opex(
            categoria="Gas", concepto="Gas LP", monto=300.0, sucursal_id=1,
        )
        # Verify gastos row was written despite GL failure
        row = self.db.execute("SELECT COUNT(*) FROM gastos").fetchone()[0]
        self.assertEqual(row, 1)

    def test_gl_metadata_includes_categoria_and_metodo(self):
        """GL entry metadata contains category and payment method for audit trail."""
        svc = self._make_svc()
        svc.registrar_gasto_opex(
            categoria="Mantenimiento", concepto="Reparación AC",
            monto=1200.0, metodo_pago="efectivo", usuario="admin", sucursal_id=2,
        )
        entry = self.finance.last()
        self.assertEqual(entry["metadata"]["categoria"], "Mantenimiento")
        self.assertEqual(entry["metadata"]["metodo_pago"], "efectivo")
        self.assertEqual(entry["sucursal_id"], 2)


# ---------------------------------------------------------------------------
# 3. TreasuryService receives finance_service from app_container (static check)
# ---------------------------------------------------------------------------

class TestAppContainerWiring(unittest.TestCase):
    """Verify app_container.py passes finance_service to TreasuryService."""

    def test_treasury_wired_with_finance_service(self):
        import os, ast

        src_path = os.path.join(
            os.path.dirname(__file__),
            "..", "core", "app_container.py",
        )
        with open(src_path) as f:
            source = f.read()

        self.assertIn("finance_service=self.finance_service", source,
                      "app_container must pass finance_service to TreasuryService")


if __name__ == "__main__":
    unittest.main(verbosity=2)
