"""FASE 7.18 (ventas) — canonical sales persistence is UUIDv7-native.

AppContainer wires ``SQLiteSalesRepository`` as ``sales_repo`` (the legacy
``repositories.sales_repository.SalesRepository`` minted identity from
``cursor.lastrowid``, which REGLA CERO forbids). These tests pin the canonical
repo's contract: sale and line-item identities are fresh UUIDv7 TEXT strings,
distinct from each other and from the operation_id, with no integer cast.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from infrastructure.persistence.sqlite_sales_repository import SQLiteSalesRepository


@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE ventas (
            id TEXT PRIMARY KEY, folio TEXT, sucursal_id TEXT, usuario TEXT,
            cliente_id TEXT, subtotal REAL, descuento REAL, total REAL,
            forma_pago TEXT, efectivo_recibido REAL, operation_id TEXT,
            observations TEXT, estado TEXT, fecha TEXT
        );
        CREATE TABLE detalles_venta (
            id TEXT PRIMARY KEY, venta_id TEXT, producto_id TEXT, cantidad REAL,
            precio_unitario REAL, subtotal REAL, costo_unitario_real REAL, descuento REAL
        );
        CREATE TABLE productos (id TEXT PRIMARY KEY, nombre TEXT);
        """
    )
    conn.commit()
    return SQLiteSalesRepository(conn)


def test_create_sale_mints_uuid_not_lastrowid(repo):
    branch = str(uuid.uuid4())
    client = str(uuid.uuid4())
    op_id = str(uuid.uuid4())
    sale_id, folio = repo.create_sale(
        branch_id=branch, user="ana", client_id=client, subtotal=100.0,
        discount=0.0, total=100.0, payment_method="Efectivo", amount_paid=100.0,
        operation_id=op_id, notes="POS",
    )
    assert uuid.UUID(sale_id)            # sale identity is a UUIDv7 string
    assert sale_id != op_id              # entity_id != operation_id (rule 41)
    row = repo.get_by_id(sale_id)
    assert row is not None
    assert row["id"] == sale_id
    assert row["sucursal_id"] == branch  # branch FK stored as the UUID string
    assert row["cliente_id"] == client


def test_save_sale_item_mints_distinct_uuid_ids(repo):
    branch = str(uuid.uuid4())
    sale_id, _ = repo.create_sale(
        branch_id=branch, user="ana", client_id=None, subtotal=50.0, discount=0.0,
        total=50.0, payment_method="Efectivo", amount_paid=50.0,
        operation_id=str(uuid.uuid4()), notes="",
    )
    product_a = str(uuid.uuid4())
    product_b = str(uuid.uuid4())
    repo._conn.execute("INSERT INTO productos VALUES (?, 'A'), (?, 'B')", (product_a, product_b))
    repo.save_sale_item(sale_id=sale_id, product_id=product_a, qty=2, unit_price=10.0, subtotal=20.0)
    repo.save_sale_item(sale_id=sale_id, product_id=product_b, qty=3, unit_price=10.0, subtotal=30.0)

    items = repo.get_items(sale_id)
    assert len(items) == 2
    ids = {it["id"] for it in items}
    assert all(uuid.UUID(i) for i in ids)        # each line has its own UUIDv7
    assert len(ids) == 2                          # distinct, not autoincrement collisions
    assert {it["producto_id"] for it in items} == {product_a, product_b}
