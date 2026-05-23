import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.order_badge_service import OrderBadgeService


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE delivery_orders (
            id INTEGER PRIMARY KEY,
            sucursal_id INTEGER,
            estado TEXT,
            adjustment_pending INTEGER DEFAULT 0
        );
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY,
            sucursal_id INTEGER,
            estado TEXT,
            workflow_type TEXT
        );
        CREATE TABLE notification_inbox (
            id INTEGER PRIMARY KEY,
            sucursal_id INTEGER,
            leido INTEGER DEFAULT 0
        );
        """
    )
    return db


def test_badge_counts_are_branch_scoped():
    db = _db()
    # branch 1
    db.execute("INSERT INTO delivery_orders VALUES (1,1,'pendiente',0)")
    db.execute("INSERT INTO delivery_orders VALUES (2,1,'preparacion',1)")
    db.execute("INSERT INTO delivery_orders VALUES (3,1,'entregado',0)")
    db.execute("INSERT INTO ventas VALUES (10,1,'programado','scheduled')")
    db.execute("INSERT INTO notification_inbox VALUES (100,1,0)")
    db.execute("INSERT INTO notification_inbox VALUES (101,1,1)")

    # branch 2 noise
    db.execute("INSERT INTO delivery_orders VALUES (4,2,'pendiente',1)")
    db.execute("INSERT INTO ventas VALUES (11,2,'programado','scheduled')")
    db.execute("INSERT INTO notification_inbox VALUES (102,2,0)")
    db.commit()

    svc = OrderBadgeService(db)
    c1 = svc.get_badge_counts(branch_id=1)
    assert c1["orders_active"] == 2
    assert c1["orders_scheduled"] == 1
    assert c1["adjustments_pending"] == 1
    assert c1["notifications_unread"] == 1

    c2 = svc.get_badge_counts(branch_id=2)
    assert c2["orders_active"] == 1
    assert c2["orders_scheduled"] == 1
    assert c2["adjustments_pending"] == 1
    assert c2["notifications_unread"] == 1


def test_badge_counts_handle_legacy_ventas_without_workflow_type():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE delivery_orders (id INTEGER PRIMARY KEY, sucursal_id INTEGER, estado TEXT);
        CREATE TABLE ventas (id INTEGER PRIMARY KEY, sucursal_id INTEGER, estado TEXT);
        CREATE TABLE notification_inbox (id INTEGER PRIMARY KEY, sucursal_id INTEGER, leido INTEGER DEFAULT 0);
        """
    )
    db.execute("INSERT INTO delivery_orders VALUES (1,1,'pendiente')")
    db.execute("INSERT INTO notification_inbox VALUES (1,1,0)")
    db.commit()

    svc = OrderBadgeService(db)
    c = svc.get_badge_counts(branch_id=1)
    assert c["orders_active"] == 1
    assert c["orders_scheduled"] == 0  # no canonical column yet
    assert c["adjustments_pending"] == 0
    assert c["notifications_unread"] == 1
