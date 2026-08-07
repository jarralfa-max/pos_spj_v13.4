"""P2 repoint — ReporteEmailService's "Lotes por vencer" KPI reads the ledger.

``_build_reporte_diario`` counted ``SELECT COUNT(*) FROM lotes WHERE
DATE(fecha_caducidad)<=? AND estado='activo'`` (legacy table). It now uses
``ExpiryQueryService.list_at_risk()`` — the same canonical read that powers the
Inventario module's expiry/cadena-de-frío alerts — over
``inventory_balances``/``inventory_lots`` (INV-7), counting lots classified
EXPIRED/CRITICAL/WARNING instead of a bare "expiration date <= today" cutoff.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.shared.ids import new_uuid
from core.services.reporte_email_service import ReporteEmailService


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.executescript(
        """
        CREATE TABLE ventas (id TEXT PRIMARY KEY, fecha TEXT, estado TEXT, total REAL DEFAULT 0);
        CREATE TABLE devoluciones (id TEXT PRIMARY KEY, fecha TEXT);
        CREATE TABLE email_schedule (id TEXT PRIMARY KEY, tipo TEXT, hora TEXT, activo INTEGER, ultimo_envio TEXT);
        """
    )
    c.commit()
    return c


def _seed_lot(conn, *, product_id, branch_id, expiration_date, quantity="5"):
    lot_id = new_uuid()
    conn.execute(
        "INSERT INTO inventory_lots (id, product_id, lot_code, origin_type, "
        "expiration_date, branch_id, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
        (lot_id, product_id, f"L-{lot_id[:8]}", "PURCHASE_RECEIPT", expiration_date, branch_id),
    )
    conn.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id, "
        "lot_id, inventory_status, quantity, updated_at) "
        "VALUES (?,?,?,?,?,'AVAILABLE',?,datetime('now'))",
        (new_uuid(), product_id, branch_id, branch_id, lot_id, quantity),
    )
    conn.commit()
    return lot_id


def test_lotes_por_vencer_counts_at_risk_canonical_lots():
    conn = _conn()
    today = date.today()
    _seed_lot(conn, product_id="p1", branch_id="b1",
              expiration_date=(today - timedelta(days=1)).isoformat())  # EXPIRED
    _seed_lot(conn, product_id="p2", branch_id="b1",
              expiration_date=(today + timedelta(days=1)).isoformat())  # CRITICAL
    _seed_lot(conn, product_id="p3", branch_id="b1",
              expiration_date=(today + timedelta(days=60)).isoformat())  # OK, no cuenta

    html = ReporteEmailService(conn)._build_reporte_diario()
    assert "Lotes por vencer" in html
    assert ">2<" in html


def test_lotes_por_vencer_zero_when_no_lots_at_risk():
    conn = _conn()
    html = ReporteEmailService(conn)._build_reporte_diario()
    assert ">0<" in html
