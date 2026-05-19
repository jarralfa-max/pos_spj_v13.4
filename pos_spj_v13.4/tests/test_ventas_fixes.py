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


# ── 2. IVA via config_service — static analysis ──────────────────────────────

class TestVentasNoDirectDbForIva(unittest.TestCase):
    """Ensure modulos/ventas.py no longer uses container.db.execute for tasa_iva."""

    _VENTAS_PATH = Path(__file__).parent.parent / "modulos" / "ventas.py"

    def _source(self) -> str:
        return self._VENTAS_PATH.read_text(encoding="utf-8")

    def test_no_direct_db_execute_for_tasa_iva(self):
        src = self._source()
        # Must not contain the old pattern: db.execute(... tasa_iva ...)
        # We check that "tasa_iva" never appears next to "db.execute"
        import re
        bad = re.findall(r'db\.execute[^)]+tasa_iva', src)
        self.assertFalse(
            bad,
            f"Direct db.execute for tasa_iva still present: {bad}",
        )

    def test_config_service_used_for_tasa_iva(self):
        src = self._source()
        self.assertIn("config_service.get('tasa_iva'", src,
                      "config_service.get('tasa_iva',...) call not found in ventas.py")


# ── 3. Stock check uses inventory_service — static analysis ──────────────────

class TestVentasNoDirectDbForStock(unittest.TestCase):
    """Ensure the stock check in ventas.py uses inventory_service, not raw SQL."""

    _VENTAS_PATH = Path(__file__).parent.parent / "modulos" / "ventas.py"

    def _source(self) -> str:
        return self._VENTAS_PATH.read_text(encoding="utf-8")

    def test_get_stock_sucursal_called(self):
        src = self._source()
        self.assertIn("get_stock_sucursal", src,
                      "inventory_service.get_stock_sucursal() call not found in ventas.py")

    def test_no_inline_single_product_stock_check(self):
        src = self._source()
        # The old single-product stock check used this pattern — it should be
        # gone, replaced by inventory_service.get_stock_sucursal().
        # (The catalog query that loads ALL products with a JOIN is allowed.)
        bad = (
            "SELECT COALESCE(bi.quantity, p.existencia, 0) FROM productos p "
            "LEFT JOIN branch_inventory"
        )
        self.assertNotIn(
            bad, src.replace("\n", " ").replace("  ", " "),
            "Old inline single-product branch_inventory stock query still present",
        )


# ── 4. No duplicate scanner fallback block ────────────────────────────────────

class TestNoDuplicateScannerBlock(unittest.TestCase):
    """The 90-line duplicate scanner-fallback block should be absent."""

    _VENTAS_PATH = Path(__file__).parent.parent / "modulos" / "ventas.py"

    def _source(self) -> str:
        return self._VENTAS_PATH.read_text(encoding="utf-8")

    def test_buscar_por_codigo_appears_only_once_as_fallback(self):
        src = self._source()
        # The duplicate block started with a comment identifying it as the
        # "fallback idéntico" — this comment should now be in the file only
        # as the removal notice, OR the pattern "# Fallback" should not
        # appear with a second scanner lookup.  Simpler: count how many times
        # the exact legacy query pattern appears.
        legacy_pattern = "SELECT * FROM productos WHERE (codigo_barras=? OR codigo=?)"
        count = src.count(legacy_pattern)
        self.assertLessEqual(
            count, 1,
            f"Duplicate scanner SQL found {count} times — expected at most 1",
        )

    def test_file_has_no_syntax_errors(self):
        src = self._source()
        try:
            ast.parse(src)
        except SyntaxError as e:
            self.fail(f"SyntaxError in ventas.py after refactor: {e}")


# ── 5. Smoke test: UnifiedInventoryService is importable ─────────────────────

class TestInventoryServiceImport(unittest.TestCase):
    def test_import(self):
        from core.services.inventory.unified_inventory_service import UnifiedInventoryService
        self.assertTrue(callable(UnifiedInventoryService))

    def test_get_stock_sucursal_exists(self):
        from core.services.inventory.unified_inventory_service import UnifiedInventoryService
        self.assertTrue(hasattr(UnifiedInventoryService, "get_stock_sucursal"))


if __name__ == "__main__":
    unittest.main()
