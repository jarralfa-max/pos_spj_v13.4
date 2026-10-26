"""Mínimos por almacén → campana existente, con deduplicación por regla."""

import sqlite3
from types import SimpleNamespace

from backend.application.inventory.notifications import stock_minimum_monitor as monitor
from backend.infrastructure.db.schema.products_schema import create_products_schema


def test_stock_minimum_alerts_are_per_warehouse_and_throttled(monkeypatch):
    conn = sqlite3.connect(":memory:")
    create_products_schema(conn)
    conn.executescript("""
        CREATE TABLE warehouses (id TEXT PRIMARY KEY, branch_id TEXT, name TEXT, status TEXT);
        CREATE TABLE inventory_replenishment_rule (
            id TEXT PRIMARY KEY, product_id TEXT, branch_id TEXT, warehouse_id TEXT,
            reorder_point TEXT, active INTEGER);
        CREATE TABLE inventory_balances (
            product_id TEXT, branch_id TEXT, warehouse_id TEXT, inventory_status TEXT,
            quantity TEXT, reserved_quantity TEXT);
        CREATE TABLE notification_inbox (
            id TEXT PRIMARY KEY, empleado_id TEXT, tipo TEXT, titulo TEXT, cuerpo TEXT,
            datos TEXT, sucursal_id TEXT, created_at TEXT, leido INTEGER DEFAULT 0);
    """)
    conn.execute("INSERT INTO products (id, code, name, product_type, base_unit_id, "
                 "lifecycle_status) VALUES ('p','P','Pollo','RESALE_PRODUCT','kg','ACTIVE')")
    conn.executemany("INSERT INTO warehouses VALUES (?,?,?,'ACTIVE')",
                     [("w1", "b1", "Tienda 1"), ("w2", "b2", "Tienda 2")])
    conn.executemany("INSERT INTO inventory_replenishment_rule VALUES (?,?,?,?,?,1)",
                     [("r1", "p", "b1", "w1", "5"),
                      ("r2", "p", "b2", "w2", "5")])
    conn.execute("INSERT INTO inventory_balances VALUES ('p','b1','w1','AVAILABLE','4','0')")
    conn.execute("INSERT INTO inventory_balances VALUES ('p','b2','w2','AVAILABLE','6','0')")

    class Settings:
        def __init__(self, _connection):
            pass

        def current(self):
            return SimpleNamespace(alerts_enabled=True, alert_roles=("almacenista",),
                                   whatsapp_enabled=False, whatsapp_phones=())

        def alert_user_ids(self, _settings, *, branch_id):
            return [f"user-{branch_id}"]

    monkeypatch.setattr(monitor, "ProductSettingsQuery", Settings)
    service = monitor.StockMinimumMonitor(conn)
    assert service.run_once() == 1
    assert service.run_once() == 0
    conn.execute("UPDATE inventory_balances SET quantity='4' WHERE warehouse_id='w2'")
    assert service.run_once() == 1
    inbox = conn.execute(
        "SELECT empleado_id, sucursal_id FROM notification_inbox ORDER BY sucursal_id"
    ).fetchall()
    assert inbox == [("user-b1", "b1"), ("user-b2", "b2")]
    conn.close()
