"""
Regression tests for surgical fixes applied to modulos/ventas.py:
  1. IVA config read via config_service (not direct DB)
  2. Stock check via inventory_service.get_stock_sucursal() (branch-aware)
  3. No duplicate scanner fallback block
"""
from __future__ import annotations
import sqlite3, ast, textwrap, unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            precio REAL DEFAULT 0,
            existencia REAL DEFAULT 0,
            stock_minimo REAL DEFAULT 0,
            activo INTEGER DEFAULT 1,
            unidad TEXT DEFAULT 'pza'
        );
        CREATE TABLE IF NOT EXISTS branch_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            branch_id INTEGER,
            quantity REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS configuraciones (
            clave TEXT PRIMARY KEY,
            valor TEXT
        );
    """)
    conn.commit()
    return conn


# ── 1. UnifiedInventoryService.get_stock_sucursal ────────────────────────────

class TestGetStockSucursal(unittest.TestCase):

    def setUp(self):
        from core.services.inventory.unified_inventory_service import UnifiedInventoryService
        self.conn = _make_db()
        self.svc = UnifiedInventoryService(conn=self.conn, sucursal_id=1)

    def _add_producto(self, pid: int, existencia: float) -> None:
        self.conn.execute(
            "INSERT INTO productos (id, nombre, precio, existencia) VALUES (?,?,?,?)",
            (pid, f"Producto {pid}", 100.0, existencia),
        )
        self.conn.commit()

    def _add_branch_inventory(self, product_id: int, branch_id: int, qty: float) -> None:
        self.conn.execute(
            "INSERT INTO branch_inventory (product_id, branch_id, quantity) VALUES (?,?,?)",
            (product_id, branch_id, qty),
        )
        self.conn.commit()

    def test_fallback_to_existencia_when_no_branch_record(self):
        self._add_producto(1, 50.0)
        result = self.svc.get_stock_sucursal(1, branch_id=1)
        self.assertAlmostEqual(result, 50.0)

    def test_branch_inventory_takes_priority(self):
        self._add_producto(2, 50.0)
        self._add_branch_inventory(2, branch_id=1, qty=30.0)
        result = self.svc.get_stock_sucursal(2, branch_id=1)
        self.assertAlmostEqual(result, 30.0)

    def test_branch_specific_stock_not_mixed(self):
        self._add_producto(3, 100.0)
        self._add_branch_inventory(3, branch_id=1, qty=15.0)
        self._add_branch_inventory(3, branch_id=2, qty=75.0)
        self.assertAlmostEqual(self.svc.get_stock_sucursal(3, branch_id=1), 15.0)
        self.assertAlmostEqual(self.svc.get_stock_sucursal(3, branch_id=2), 75.0)

    def test_missing_product_returns_zero(self):
        result = self.svc.get_stock_sucursal(9999, branch_id=1)
        self.assertAlmostEqual(result, 0.0)

    def test_uses_instance_sucursal_id_when_no_branch_id_given(self):
        self._add_producto(4, 20.0)
        self._add_branch_inventory(4, branch_id=1, qty=12.0)
        svc = __import__(
            "core.services.inventory.unified_inventory_service",
            fromlist=["UnifiedInventoryService"],
        ).UnifiedInventoryService(conn=self.conn, sucursal_id=1)
        self.assertAlmostEqual(svc.get_stock_sucursal(4), 12.0)

    def test_zero_branch_quantity_returned_not_existencia(self):
        self._add_producto(5, 100.0)
        self._add_branch_inventory(5, branch_id=1, qty=0.0)
        result = self.svc.get_stock_sucursal(5, branch_id=1)
        self.assertAlmostEqual(result, 0.0)


# modulos/ventas.py (legacy) retirado (SALES-22) — TestVentasNoDirectDbForIva,
# TestVentasNoDirectDbForStock y TestNoDuplicateScannerBlock leían
# exclusivamente su código fuente y se retiraron con él.


# ── 5. Phase 4: repository usage (shared repos/container, real regardless of
#       modulos/ventas.py's retirement — SALES-22) ───────────────────────────

class TestVentasPhase4Repos(unittest.TestCase):

    def test_ClienteRepository_has_get_by_scanner(self):
        from repositories.cliente_repository import ClienteRepository
        self.assertTrue(hasattr(ClienteRepository, "get_by_scanner"))

    def test_ProductoRepository_has_get_by_barcode(self):
        from repositories.productos import ProductoRepository
        self.assertTrue(hasattr(ProductoRepository, "get_by_barcode"))

    def test_ProductoRepository_wired_in_container(self):
        src = Path(__file__).parent.parent.joinpath("core/app_container.py").read_text()
        self.assertIn("ProductoRepository", src,
                      "ProductoRepository not imported in app_container.py")
        self.assertIn("producto_repo", src,
                      "producto_repo not wired in AppContainer")


# ── 6. Smoke test: UnifiedInventoryService is importable ─────────────────────

class TestInventoryServiceImport(unittest.TestCase):
    def test_import(self):
        from core.services.inventory.unified_inventory_service import UnifiedInventoryService
        self.assertTrue(callable(UnifiedInventoryService))

    def test_get_stock_sucursal_exists(self):
        from core.services.inventory.unified_inventory_service import UnifiedInventoryService
        self.assertTrue(hasattr(UnifiedInventoryService, "get_stock_sucursal"))


if __name__ == "__main__":
    unittest.main()
