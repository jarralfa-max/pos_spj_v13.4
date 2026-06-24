"""Protection tests for the ConnectionUnitOfWork transaction boundary in
ProductCatalogService (F3). Verify commit-on-success and rollback-on-error
without any explicit commit()/rollback() in the service.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.services.product_catalog_service import ProductCatalogService


class _SpyConn:
    """Wraps a real sqlite connection, counting commit/rollback calls."""

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real
        self.commits = 0
        self.rollbacks = 0

    def execute(self, *a, **k):
        return self._real.execute(*a, **k)

    def cursor(self):
        return self._real.cursor()

    def commit(self):
        self.commits += 1
        self._real.commit()

    def rollback(self):
        self.rollbacks += 1
        self._real.rollback()


@pytest.fixture
def conn():
    real = sqlite3.connect(":memory:")
    real.row_factory = sqlite3.Row
    real.executescript(
        """
        CREATE TABLE productos (
            id TEXT PRIMARY KEY, nombre TEXT, codigo TEXT, codigo_barras TEXT,
            categoria TEXT, precio REAL, precio_compra REAL, precio_minimo_venta REAL,
            unidad TEXT, stock_minimo REAL, tipo_producto TEXT, es_compuesto INTEGER,
            es_subproducto INTEGER, imagen_path TEXT, existencia REAL DEFAULT 0,
            oculto INTEGER DEFAULT 0, activo INTEGER DEFAULT 1
        );
        INSERT INTO productos (id, nombre, activo, oculto) VALUES ('p-uuid-1','Pechuga',1,0);
        """
    )
    real.commit()
    return _SpyConn(real)


def test_set_product_state_commits_on_success(conn):
    svc = ProductCatalogService(conn)
    svc.deactivate_product("p-uuid-1", operation_id="op-1", user_name="ana")

    assert conn.commits == 1 and conn.rollbacks == 0
    row = conn.execute("SELECT activo, oculto FROM productos WHERE id='p-uuid-1'").fetchone()
    assert (row["activo"], row["oculto"]) == (0, 1)


def test_restore_product_commits_and_clears_hidden(conn):
    svc = ProductCatalogService(conn)
    svc.deactivate_product("p-uuid-1", operation_id="op-1")
    svc.restore_product("p-uuid-1", operation_id="op-2")

    row = conn.execute("SELECT activo, oculto FROM productos WHERE id='p-uuid-1'").fetchone()
    assert (row["activo"], row["oculto"]) == (1, 0)
    assert conn.rollbacks == 0


def test_create_product_rolls_back_on_error(conn):
    svc = ProductCatalogService(conn)

    class _BadCmd:
        name = "X"
        category = "C"
        unit = "kg"
        purchase_price = 0
        minimum_sale_price = 0
        operation_id = "op-err"
        # force a NOT NULL / datatype failure path by giving precio a bad type
        price = object()  # float(object()) -> TypeError inside the with-block

    with pytest.raises(Exception):
        svc.create_product(_BadCmd())

    # No partial row, rollback driven by the UnitOfWork.
    assert conn.execute("SELECT COUNT(*) FROM productos WHERE nombre='X'").fetchone()[0] == 0
    assert conn.rollbacks == 1 and conn.commits == 0


def test_create_product_commits_on_success(conn):
    svc = ProductCatalogService(conn)

    class _Cmd:
        name = "Molida"
        category = "Res"
        unit = "kg"
        price = 130.0
        purchase_price = 80.0
        minimum_sale_price = 0
        product_type = "simple"
        operation_id = "op-ok"

    result = svc.create_product(_Cmd())

    assert result.success and conn.commits == 1 and conn.rollbacks == 0
    assert conn.execute("SELECT COUNT(*) FROM productos WHERE nombre='Molida'").fetchone()[0] == 1
