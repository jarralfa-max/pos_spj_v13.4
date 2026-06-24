"""Protection tests for compras write SQL extracted from compras_pro.py.

Verify the repo executes the right mutations and that, driven by
ConnectionUnitOfWork, the assignment (UPDATE + DELETE + re-INSERT) commits as a
unit and rolls back atomically on error. PyQt-free; headless.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.repositories.compras_write_repository import (
    ComprasWriteRepository,
)
from backend.infrastructure.db.unit_of_work import ConnectionUnitOfWork


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE contenedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE, tipo TEXT,
            descripcion TEXT, estado TEXT, usuario_creado TEXT, parent_id INTEGER,
            sucursal_destino INTEGER, observaciones TEXT, proveedor_id INTEGER,
            comprador TEXT, folio_factura TEXT, fecha_factura TEXT, metodo_pago TEXT,
            forma_pago TEXT, plazo_dias INTEGER, vence_pago TEXT, total REAL,
            fecha_asignado TEXT, usuario_asign TEXT
        );
        CREATE TABLE contenedor_productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, contenedor_id INTEGER,
            producto_id INTEGER, cantidad REAL, costo_unitario REAL,
            cantidad_recibida REAL, usuario_recibe TEXT, recibido_por TEXT
        );
        ALTER TABLE contenedores ADD COLUMN fecha_recibido TEXT;
        ALTER TABLE contenedores ADD COLUMN usuario_recibe TEXT;
        ALTER TABLE contenedores ADD COLUMN recibido_por TEXT;
        CREATE TABLE productos (id INTEGER PRIMARY KEY, existencia REAL);
        CREATE TABLE compras (id INTEGER PRIMARY KEY, estado TEXT);
        INSERT INTO contenedores (id, codigo, tipo, estado) VALUES (1,'C-1','caja','generado');
        INSERT INTO contenedor_productos (contenedor_id, producto_id, cantidad, costo_unitario)
            VALUES (1, 9, 1.0, 1.0);
        INSERT INTO productos VALUES (9, 5.0);
        INSERT INTO compras VALUES (1, 'para_recepcion');
        """
    )
    conn.commit()
    return conn


@pytest.fixture
def repo(db):
    return ComprasWriteRepository(db)


def test_insert_container(repo, db):
    with ConnectionUnitOfWork(db):
        repo.insert_container(codigo="C-2", tipo="tarima", descripcion="x",
                              usuario_creado="ana", parent_id=None,
                              sucursal_destino=1, observaciones=None)
    row = db.execute("SELECT tipo, estado, usuario_creado FROM contenedores WHERE codigo='C-2'").fetchone()
    assert (row["tipo"], row["estado"], row["usuario_creado"]) == ("tarima", "generado", "ana")


def test_assign_container_sets_fields_and_state(repo, db):
    with ConnectionUnitOfWork(db):
        repo.assign_container(1, proveedor_id=7, comprador="leo", folio_factura="F1",
                              fecha_factura="2026-06-01", metodo_pago="efectivo",
                              forma_pago="contado", plazo_dias=0, vence_pago=None,
                              sucursal_destino=1, total=250.0, usuario_asign="leo")
    row = db.execute("SELECT proveedor_id, estado, total FROM contenedores WHERE id=1").fetchone()
    assert (row["proveedor_id"], row["estado"], row["total"]) == (7, "asignado", 250.0)


def test_replace_container_products_is_atomic_swap(repo, db):
    items = [{"producto_id": 1, "cantidad": 2.0, "costo": 40.0},
             {"producto_id": 2, "cantidad": 3.0, "costo": 15.0}]
    with ConnectionUnitOfWork(db):
        repo.replace_container_products(1, items)
    rows = db.execute(
        "SELECT producto_id, cantidad, costo_unitario FROM contenedor_productos "
        "WHERE contenedor_id=1 ORDER BY producto_id"
    ).fetchall()
    # old product 9 removed, two new ones present
    assert [tuple(r) for r in rows] == [(1, 2.0, 40.0), (2, 3.0, 15.0)]


def test_reception_marks_container_qty_and_stock_atomically(repo, db):
    with ConnectionUnitOfWork(db):
        repo.mark_container_received(1, estado="recibido", usuario_recibe="ana",
                                     recibido_por="ana", observaciones=None)
        repo.set_received_quantity(1, 9, 3.0)
        repo.increase_product_stock(9, 3.0)
    cont = db.execute("SELECT estado, recibido_por FROM contenedores WHERE id=1").fetchone()
    assert (cont["estado"], cont["recibido_por"]) == ("recibido", "ana")
    cp = db.execute("SELECT cantidad_recibida FROM contenedor_productos WHERE contenedor_id=1 AND producto_id=9").fetchone()
    assert cp["cantidad_recibida"] == 3.0
    assert db.execute("SELECT existencia FROM productos WHERE id=9").fetchone()["existencia"] == 8.0


def test_update_purchase_status(repo, db):
    with ConnectionUnitOfWork(db):
        repo.update_purchase_status(1, "completada")
    assert db.execute("SELECT estado FROM compras WHERE id=1").fetchone()["estado"] == "completada"


def test_assignment_rolls_back_on_error(repo, db):
    """If the product re-insert fails mid-way, the UoW rolls back the whole swap."""
    bad_items = [{"producto_id": 1, "cantidad": 2.0, "costo": 40.0},
                 {"producto_id": 2, "cantidad": "NaN-not-float", "costo": 15.0}]
    with pytest.raises(Exception):
        with ConnectionUnitOfWork(db):
            repo.assign_container(1, proveedor_id=7, comprador="leo", folio_factura=None,
                                  fecha_factura=None, metodo_pago="x", forma_pago="y",
                                  plazo_dias=0, vence_pago=None, sucursal_destino=1,
                                  total=99.0, usuario_asign="leo")
            repo.replace_container_products(1, bad_items)
    # rolled back: assignment NOT applied, original product line intact
    row = db.execute("SELECT estado, proveedor_id FROM contenedores WHERE id=1").fetchone()
    assert row["estado"] == "generado" and row["proveedor_id"] is None
    prods = db.execute("SELECT producto_id FROM contenedor_productos WHERE contenedor_id=1").fetchall()
    assert [r["producto_id"] for r in prods] == [9]
