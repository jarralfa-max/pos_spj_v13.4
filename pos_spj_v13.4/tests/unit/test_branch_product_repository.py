"""Protection tests for branch-product / price-history SQL extracted from productos.py.

These pin the behaviour the PyQt UI used to implement inline (F5 extraction,
regla 4). PyQt-free, so they actually run in CI without a Qt runtime.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.repositories.branch_product_repository import (
    BranchProductRepository,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE sucursales (id INTEGER PRIMARY KEY, nombre TEXT, activa INTEGER DEFAULT 1);
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, precio REAL DEFAULT 0,
                                precio_compra REAL DEFAULT 0, activo INTEGER DEFAULT 1);
        CREATE TABLE branch_products (
            branch_id INTEGER, product_id INTEGER, activo INTEGER DEFAULT 1,
            precio_local REAL, stock_min_local REAL, updated_at TEXT,
            UNIQUE(branch_id, product_id)
        );
        CREATE TABLE historial_precios (
            id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER, campo TEXT,
            precio_anterior REAL, precio_nuevo REAL, diferencia_pct REAL,
            usuario TEXT, changed_at TEXT
        );
        INSERT INTO sucursales VALUES (1,'Centro',1),(2,'Norte',1),(3,'Sur',0);
        INSERT INTO productos  VALUES (1,'Pechuga',95.0,60.0,1),(2,'Pierna',75.0,45.0,1);
        INSERT INTO branch_products VALUES (1,1,1,90.0,4.0,NULL);
        INSERT INTO historial_precios (producto_id,campo,precio_anterior,precio_nuevo,diferencia_pct,usuario,changed_at)
        VALUES (1,'precio',90.0,95.0,5.5,'ana','2026-01-01'),
               (1,'precio',85.0,90.0,5.8,'ana','2026-02-01');
        """
    )
    conn.commit()
    return conn


@pytest.fixture
def repo(db):
    return BranchProductRepository(db)


def test_list_active_branches_excludes_inactive_ordered_by_id(repo):
    assert repo.list_active_branches() == [
        {"id": 1, "nombre": "Centro"},
        {"id": 2, "nombre": "Norte"},
    ]


def test_list_branch_products_filtered_by_branch(repo):
    rows = repo.list_branch_products(branch_id=1)
    assert len(rows) == 1
    assert rows[0]["prod_nombre"] == "Pechuga"
    assert rows[0]["precio_local"] == 90.0
    assert rows[0]["precio_global"] == 95.0
    assert (rows[0]["branch_id"], rows[0]["product_id"]) == (1, 1)


def test_list_branch_products_all_branches_when_no_filter(repo):
    assert repo.list_branch_products(branch_id=None) == repo.list_branch_products()


def test_inactive_branches_for_product_lists_active_branches_without_active_config(repo):
    # Product 1 is active-configured only in branch 1; branches 2 (Norte) lack a row -> inactive.
    txt = repo.inactive_branches_for_product(product_id=1)
    assert txt is not None and "Norte" in txt
    # Sur is inactive sucursal -> never listed
    assert "Sur" not in txt


def test_get_product_basic(repo):
    assert repo.get_product_basic(1) == {"nombre": "Pechuga", "precio": 95.0, "precio_compra": 60.0}
    assert repo.get_product_basic(999) is None


def test_list_price_history_newest_first(repo):
    rows = repo.list_price_history(1)
    assert [r["changed_at"] for r in rows] == ["2026-02-01", "2026-01-01"]


def test_upsert_inserts_new_branch_product(repo, db):
    repo.upsert_branch_product(branch_id=2, product_id=2, activo=1, precio_local=80.0, stock_min_local=3.0)
    db.commit()
    row = db.execute(
        "SELECT activo, precio_local, stock_min_local FROM branch_products WHERE branch_id=2 AND product_id=2"
    ).fetchone()
    assert (row["activo"], row["precio_local"], row["stock_min_local"]) == (1, 80.0, 3.0)


def test_upsert_updates_existing_without_duplicating(repo, db):
    repo.upsert_branch_product(branch_id=1, product_id=1, activo=0, precio_local=99.0, stock_min_local=7.0)
    db.commit()
    rows = db.execute("SELECT * FROM branch_products WHERE branch_id=1 AND product_id=1").fetchall()
    assert len(rows) == 1
    assert (rows[0]["activo"], rows[0]["precio_local"], rows[0]["stock_min_local"]) == (0, 99.0, 7.0)


def test_upsert_stores_null_for_zero_overrides(repo, db):
    repo.upsert_branch_product(branch_id=2, product_id=1, activo=1, precio_local=None, stock_min_local=None)
    db.commit()
    row = db.execute(
        "SELECT precio_local, stock_min_local FROM branch_products WHERE branch_id=2 AND product_id=1"
    ).fetchone()
    assert row["precio_local"] is None and row["stock_min_local"] is None
