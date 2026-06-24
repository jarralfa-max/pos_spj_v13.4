"""Protection tests for VENTAS read SQL extracted from ventas.py (Fase A).

PyQt-free; run headless. Pin the behaviour of the ticket-reprint, sale-lookup
and QR-container reads the UI used to run inline.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.repositories.sales_read_repository import SalesReadRepository


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY, folio TEXT, fecha TEXT, usuario TEXT,
            forma_pago TEXT, efectivo_recibido REAL, cambio REAL, total REAL, estado TEXT
        );
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT);
        CREATE TABLE detalles_venta (
            venta_id INTEGER, producto_id INTEGER, nombre TEXT,
            cantidad REAL, precio_unitario REAL, subtotal REAL
        );
        CREATE TABLE trazabilidad_qr (uuid_qr TEXT, descripcion TEXT);
        INSERT INTO ventas VALUES (10,'F-001','2026-06-01 10:00','ana','Efectivo',100.0,5.0,95.0,'completada');
        INSERT INTO productos VALUES (1,'Pechuga','kg');
        INSERT INTO detalles_venta VALUES (10,1,'Pechuga',2.0,40.0,80.0);
        INSERT INTO detalles_venta VALUES (10,1,'Pierna',1.0,15.0,15.0);
        INSERT INTO trazabilidad_qr VALUES ('abc-uuid','Caja 5kg');
        """
    )
    conn.commit()
    return conn


@pytest.fixture
def repo(db):
    return SalesReadRepository(db)


def test_get_qr_container(repo):
    assert repo.get_qr_container("abc-uuid") == {"uuid_qr": "abc-uuid", "descripcion": "Caja 5kg"}
    assert repo.get_qr_container("missing") is None


def test_get_sale_ticket_header(repo):
    h = repo.get_sale_ticket_header(10)
    assert h["folio"] == "F-001" and h["usuario"] == "ana"
    assert (h["efectivo_recibido"], h["cambio"], h["total"]) == (100.0, 5.0, 95.0)
    assert repo.get_sale_ticket_header(999) is None


def test_get_sale_items_with_product(repo):
    items = repo.get_sale_items_with_product(10)
    # joins on producto_id=1 -> both rows resolve to 'Pechuga' product name
    assert len(items) == 2
    assert items[0] == {"nombre": "Pechuga", "cantidad": 2.0, "precio_unitario": 40.0,
                        "total": 80.0, "unidad": "kg"}


def test_find_sale_by_folio_or_id(repo):
    assert repo.find_sale_by_folio_or_id("F-001")["id"] == 10
    assert repo.find_sale_by_folio_or_id("10")["folio"] == "F-001"  # CAST(id AS TEXT)
    assert repo.find_sale_by_folio_or_id("nope") is None


def test_get_sale_items_basic_returns_tuples(repo):
    items = repo.get_sale_items_basic(10)
    assert items == [("Pechuga", 2.0, 40.0, 80.0), ("Pierna", 1.0, 15.0, 15.0)]
