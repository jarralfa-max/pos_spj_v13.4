"""Protection tests for product lookups + bulk-import SQL extracted from productos.py (F5).

These pin the behaviour of the scanner lookup and the Excel-import upsert that
used to live inline in the PyQt UI (regla 4). PyQt-free; run headless.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.repositories.product_repository import ProductRepository


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT, codigo TEXT DEFAULT '', codigo_barras TEXT DEFAULT '',
            categoria TEXT, precio REAL DEFAULT 0, precio_compra REAL DEFAULT 0,
            unidad TEXT DEFAULT 'kg', stock_minimo REAL DEFAULT 0,
            existencia REAL DEFAULT 0, activo INTEGER DEFAULT 1
        );
        INSERT INTO productos (nombre,codigo,codigo_barras,precio) VALUES
            ('Pechuga','P001','7501234567890',95.0),
            ('Pierna','P002','',75.0);
        """
    )
    conn.commit()
    return conn


@pytest.fixture
def repo(db):
    return ProductRepository(db)


def test_find_id_by_barcode_matches(repo):
    assert repo.find_id_by_barcode_or_code("7501234567890") == "1"


def test_find_id_by_code_matches(repo):
    assert repo.find_id_by_barcode_or_code("P002") == "2"


def test_find_id_by_barcode_or_code_none_when_absent(repo):
    assert repo.find_id_by_barcode_or_code("nope") is None


def test_find_id_by_name_or_code(repo):
    assert repo.find_id_by_name_or_code("Pechuga", "") == "1"
    assert repo.find_id_by_name_or_code("X", "P002") == "2"
    assert repo.find_id_by_name_or_code("X", "") is None


def test_find_id_by_name_or_code_ignores_empty_code_collision(repo):
    # codigo='' must not match other rows with empty codigo
    assert repo.find_id_by_name_or_code("Inexistente", "") is None


def test_update_basic_fields_from_import(repo, db):
    repo.update_basic_fields_from_import(
        "1", precio=120.0, precio_compra=70.0, categoria="Aves",
        unidad="kg", stock_minimo=2.0)
    db.commit()
    row = db.execute("SELECT precio, precio_compra, categoria, unidad, stock_minimo FROM productos WHERE id=1").fetchone()
    assert tuple(row) == (120.0, 70.0, "Aves", "kg", 2.0)


def test_insert_from_import_sets_zero_stock_and_active(repo, db):
    repo.insert_from_import(
        nombre="Molida", codigo="P003", codigo_barras="111", categoria="Res",
        precio=130.0, precio_compra=80.0, unidad="kg", stock_minimo=5.0)
    db.commit()
    row = db.execute("SELECT existencia, activo, precio FROM productos WHERE nombre='Molida'").fetchone()
    assert (row["existencia"], row["activo"], row["precio"]) == (0, 1, 130.0)
