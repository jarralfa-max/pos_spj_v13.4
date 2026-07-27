"""FASE 4 (delivery) — driver-settlement use case must be UUIDv7-native.

driver_id / order_ids / branch_id flow as str (UUID), order_id is stored as a
string in delivery_cut_items (UUID-ready), and integer identities are rejected
at the command boundary (REGLA CERO). The use case still works against the
current INTEGER delivery_orders.id via SQLite type affinity (str '5' matches 5).
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from backend.application.use_cases.settle_delivery_driver_use_case import (
    SettleDeliveryDriverCommand,
    SettleDeliveryDriverUseCase,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE delivery_driver_cuts (
            id TEXT PRIMARY KEY, driver_id TEXT, driver_nombre TEXT, turno_inicio TEXT,
            entregas_total INTEGER, efectivo_cobrado REAL, tarjeta_cobrado REAL,
            transfer_cobrado REAL, total_cobrado REAL, efectivo_entregado REAL,
            diferencia REAL, usuario_corte TEXT, sucursal_id TEXT, notas TEXT
        );
        CREATE TABLE delivery_cut_items (
            id TEXT PRIMARY KEY, cut_id TEXT, order_id TEXT, cliente_nombre TEXT,
            total REAL, pago_metodo TEXT, pago_monto REAL
        );
        CREATE TABLE delivery_orders (
            id INTEGER PRIMARY KEY, cliente_nombre TEXT, total REAL, pago_metodo TEXT,
            pago_monto REAL, corte_id TEXT
        );
        INSERT INTO delivery_orders (id, cliente_nombre, total, pago_metodo, pago_monto)
            VALUES (5,'Ana',100.0,'efectivo',100.0),(6,'Leo',50.0,'tarjeta',50.0);
        """
    )
    conn.commit()
    return conn


def _cmd(**kw):
    base = dict(
        driver_id=str(uuid.uuid4()), driver_nombre="Repartidor",
        order_ids=["5", "6"], efectivo_entregado=140.0, efectivo_cobrado=150.0,
        usuario="ana", sucursal_id=str(uuid.uuid4()),
    )
    base.update(kw)
    return SettleDeliveryDriverCommand(**base)


def test_settle_creates_cut_and_items_with_uuid(db):
    result = SettleDeliveryDriverUseCase(db).execute(_cmd())
    assert uuid.UUID(result["cut_id"])  # cut_id is a UUID
    items = db.execute("SELECT order_id FROM delivery_cut_items ORDER BY order_id").fetchall()
    assert [r["order_id"] for r in items] == ["5", "6"]
    # order_id stored as string (UUID-ready), not int
    assert all(isinstance(r["order_id"], str) for r in items)


def test_delivery_cut_items_order_id_maps_to_delivery_orders(db):
    SettleDeliveryDriverUseCase(db).execute(_cmd(order_ids=["5"]))
    # the cut item's order_id resolves to a real delivery_orders row (affinity)
    row = db.execute(
        "SELECT o.cliente_nombre FROM delivery_cut_items i "
        "JOIN delivery_orders o ON o.id = i.order_id WHERE i.order_id='5'"
    ).fetchone()
    assert row["cliente_nombre"] == "Ana"
    # order marked with the cut
    assert db.execute("SELECT corte_id FROM delivery_orders WHERE id=5").fetchone()["corte_id"]


def test_settle_delivery_driver_rejects_integer_order_ids(db):
    with pytest.raises(ValueError, match="order_ids.*UUID|str"):
        _cmd(order_ids=[5, 6])  # integer ids forbidden (REGLA CERO)


def test_settle_delivery_driver_rejects_integer_driver_id(db):
    with pytest.raises(ValueError, match="driver_id.*str|UUID"):
        _cmd(driver_id=7)
