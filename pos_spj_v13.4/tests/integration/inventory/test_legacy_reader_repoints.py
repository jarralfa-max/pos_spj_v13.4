"""INV-27 — legacy readers repointed to the canonical projection (flag-gated).

Each reader is backward-compatible: with the cutover flag OFF it reads the legacy
source (the live write path); with the flag ON it reads inventory_balances.
"""

import sqlite3

import pytest

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.execute("CREATE TABLE productos (id TEXT PRIMARY KEY, nombre TEXT, precio REAL,"
              " oculto INT DEFAULT 0, activo INT DEFAULT 1, unidad TEXT, categoria TEXT,"
              " stock_minimo REAL, imagen_path TEXT, es_compuesto INT DEFAULT 0,"
              " es_subproducto INT DEFAULT 0, codigo_barras TEXT, codigo TEXT)")
    c.execute("INSERT INTO productos (id,nombre,precio,stock_minimo) VALUES ('p1','P',10.0,2)")
    c.execute("CREATE TABLE inventory_stock (product_id TEXT, branch_id TEXT,"
              " quantity REAL, unit TEXT)")
    c.execute("INSERT INTO inventory_stock VALUES ('p1','b1',50.0,'u')")
    c.execute("INSERT INTO inventory_balances (id,product_id,branch_id,warehouse_id,"
              "inventory_status,quantity,reserved_quantity,updated_at)"
              " VALUES ('x','p1','b1','b1','AVAILABLE','9','0',datetime('now'))")
    c.commit()
    yield c
    c.close()


class TestProductCatalogRepoint:
    def _svc(self, conn):
        from core.services.sales.product_catalog_query_service import (
            ProductCatalogQueryService,
        )
        return ProductCatalogQueryService(conn)

    def test_flag_off_reads_legacy_inventory_stock(self, conn, monkeypatch):
        monkeypatch.delenv("INVENTORY_CANONICAL_CUTOVER", raising=False)
        rows = self._svc(conn).list_visible_products(branch_id="b1")
        assert rows[0]["existencia"] == 50.0

    def test_flag_on_reads_canonical_balances(self, conn, monkeypatch):
        monkeypatch.setenv("INVENTORY_CANONICAL_CUTOVER", "1")
        rows = self._svc(conn).list_visible_products(branch_id="b1")
        assert rows[0]["existencia"] == 9.0  # 9 available (quantity − reserved)


class TestInventoryBalanceQueryRepoint:
    def _svc(self, conn):
        from backend.application.queries.inventory_balance_service import (
            InventoryBalanceQueryService,
        )
        conn.execute("CREATE TABLE IF NOT EXISTS stock_reservas (id TEXT, estado TEXT,"
                     " branch_id TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS stock_reserva_detalles (id TEXT,"
                     " reserva_id TEXT, producto_id TEXT, cantidad REAL)")
        conn.execute("UPDATE inventory_balances SET reserved_quantity='2'"
                     " WHERE product_id='p1'")
        conn.commit()
        return InventoryBalanceQueryService(conn)

    def test_flag_off_reads_legacy(self, conn, monkeypatch):
        from decimal import Decimal
        monkeypatch.delenv("INVENTORY_CANONICAL_CUTOVER", raising=False)
        b = self._svc(conn).get_product_balance("p1", "b1")
        assert b["stock_fisico"] == Decimal("50") and b["fuente"] == "inventory_stock"

    def test_flag_on_reads_canonical(self, conn, monkeypatch):
        from decimal import Decimal
        monkeypatch.setenv("INVENTORY_CANONICAL_CUTOVER", "1")
        b = self._svc(conn).get_product_balance("p1", "b1")
        assert b["fuente"] == "inventory_balances"
        assert b["stock_fisico"] == Decimal("9") and b["stock_reservado"] == Decimal("2")
        assert b["stock_disponible"] == Decimal("7")


class TestBiInventoryRepoint:
    def _svc(self, conn):
        from backend.application.queries.bi_inventory_query_service import (
            BiInventoryQueryService,
        )
        # add cost + a critical-stock scenario
        conn.execute("ALTER TABLE productos ADD COLUMN costo REAL")
        conn.execute("ALTER TABLE productos ADD COLUMN precio_compra REAL")
        conn.execute("ALTER TABLE productos ADD COLUMN costo_promedio REAL")
        conn.execute("UPDATE productos SET costo=2.0, stock_minimo=100 WHERE id='p1'")
        conn.commit()
        return BiInventoryQueryService(conn)

    class _F:
        branch_id = "b1"
        date_from = "2000-01-01"
        date_to = "2100-01-01"

    def test_flag_off_valuation_from_legacy(self, conn, monkeypatch):
        monkeypatch.delenv("INVENTORY_CANONICAL_CUTOVER", raising=False)
        assert self._svc(conn).inventory_valued(self._F()) == 100.0  # 50 legacy * 2

    def test_flag_on_valuation_from_canonical(self, conn, monkeypatch):
        monkeypatch.setenv("INVENTORY_CANONICAL_CUTOVER", "1")
        svc = self._svc(conn)
        # canonical quantity is 9 (reserved 0 for valuation) → 9 * 2
        assert svc.inventory_valued(self._F()) == 18.0
        crit = svc.critical_stock(self._F())
        assert crit and crit[0]["existencia"] == 9.0


class TestTransferDispatchRepoint:
    def _src(self, conn):
        from backend.application.queries.transfer_query_service import (
            SQLiteTransferQueryDataSource,
        )
        conn.execute("ALTER TABLE productos ADD COLUMN existencia REAL DEFAULT 0")
        conn.commit()
        return SQLiteTransferQueryDataSource(conn)

    def test_flag_off_dispatch_stock_legacy(self, conn, monkeypatch):
        monkeypatch.delenv("INVENTORY_CANONICAL_CUTOVER", raising=False)
        rows = self._src(conn).list_products_for_dispatch("b1")
        assert rows[0]["existencia"] == 50.0

    def test_flag_on_dispatch_stock_canonical(self, conn, monkeypatch):
        monkeypatch.setenv("INVENTORY_CANONICAL_CUTOVER", "1")
        rows = self._src(conn).list_products_for_dispatch("b1")
        assert rows[0]["existencia"] == 9.0
