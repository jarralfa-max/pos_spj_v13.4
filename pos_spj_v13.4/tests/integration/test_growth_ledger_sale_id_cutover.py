"""FASE 4 (growth) — retire the duplicate sale/redeem credit path.

REGLA CERO: ``growth_ledger.ticket_id`` must stop receiving new *sale*
references. The live, canonical loyalty crediting is ``LoyaltyService`` →
``loyalty_ledger.referencia=str(venta_id)`` (already UUID-ready), so the
parallel GrowthEngine sale/redeem path is deprecated and raises, pointing
callers at the canonical service. The live nightly liability-expiration cron
(``ejecutar_expiracion_nocturna``) keeps working on ``growth_ledger`` and writes
NO sale reference (ticket_id stays NULL).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta

import pytest

from core.services.growth_engine import GrowthEngine


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, apellido TEXT, puntos INTEGER DEFAULT 0)"
    )
    conn.execute("INSERT INTO clientes (id, nombre) VALUES (1,'Ana')")
    conn.execute(
        """CREATE TABLE loyalty_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL,
            tipo TEXT NOT NULL, puntos INTEGER NOT NULL, monto_equiv REAL DEFAULT 0,
            saldo_post INTEGER DEFAULT 0, referencia TEXT DEFAULT '',
            descripcion TEXT DEFAULT '', sucursal_id INTEGER DEFAULT 1,
            usuario TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')))"""
    )
    conn.execute(
        "CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)"
    )
    conn.commit()
    return conn


def _engine(db):
    return GrowthEngine(db, sucursal_id=str(uuid.uuid4()))


def test_procesar_venta_is_deprecated_and_writes_no_growth_ledger_sale_ref(db):
    eng = _engine(db)
    before = db.execute("SELECT COUNT(*) FROM growth_ledger").fetchone()[0]
    with pytest.raises(RuntimeError, match="LoyaltyService|deprecad"):
        eng.procesar_venta(cliente_id=1, sale_id=str(uuid.uuid4()), cajero_id=0, subtotal=100.0)
    after = db.execute("SELECT COUNT(*) FROM growth_ledger").fetchone()[0]
    assert after == before  # nothing written to the duplicate ledger


def test_canjear_estrellas_is_deprecated(db):
    eng = _engine(db)
    with pytest.raises(RuntimeError, match="LoyaltyService|deprecad"):
        eng.canjear_estrellas(cliente_id=1, cajero_id=0, subtotal=100.0,
                              estrellas_a_canjear=10, sale_id=str(uuid.uuid4()))


def test_creditar_rejects_integer_sale_id(db):
    eng = _engine(db)
    with pytest.raises(ValueError, match="sale_id.*str|sale_id.*UUID"):
        eng._creditar(1, 10, 5, 0, operacion="VENTA")  # int sale_id forbidden


def test_expiracion_cron_still_runs_and_writes_no_sale_reference(db):
    eng = _engine(db)
    # seed an old, vigent star credit with NO recent purchase → expirable
    old = (datetime.now() - timedelta(days=200)).isoformat()
    db.execute(
        "INSERT INTO growth_ledger (cliente_id, sucursal_id, tipo, monto, moneda, "
        "ticket_id, cajero_id, operacion, expira_en, revertido, created_at) "
        "VALUES (1, ?, 'credito', 50, 'estrellas', NULL, 0, 'VENTA', NULL, 0, ?)",
        (eng.sucursal_id, old),
    )
    db.commit()
    n = eng.ejecutar_expiracion_nocturna()
    assert n == 1  # one client expired
    # the EXPIRACION debit carries no sale reference
    rows = db.execute(
        "SELECT ticket_id FROM growth_ledger WHERE operacion='EXPIRACION'"
    ).fetchall()
    assert rows and all(r["ticket_id"] is None for r in rows)
