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


def test_badge_counts_scoped_by_uuid_branch_post_cut():
    """Post-cut: sucursal_id is TEXT UUIDv7; the branch filter must scope by the
    UUID string (no int() cast). Regression for main_window._refresh_order_badges
    crashing with int('019f0198-...') on the cut DB.
    """
    import uuid

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE delivery_orders (id TEXT PRIMARY KEY, sucursal_id TEXT, estado TEXT, adjustment_pending INTEGER DEFAULT 0);
        CREATE TABLE ventas (id TEXT PRIMARY KEY, sucursal_id TEXT, estado TEXT, workflow_type TEXT);
        CREATE TABLE notification_inbox (id TEXT PRIMARY KEY, sucursal_id TEXT, leido INTEGER DEFAULT 0);
        """
    )
    branch_a = str(uuid.uuid4())
    branch_b = str(uuid.uuid4())
    db.execute("INSERT INTO delivery_orders VALUES (?,?,?,?)", (str(uuid.uuid4()), branch_a, "pendiente", 1))
    db.execute("INSERT INTO delivery_orders VALUES (?,?,?,?)", (str(uuid.uuid4()), branch_a, "en_ruta", 0))
    db.execute("INSERT INTO ventas VALUES (?,?,?,?)", (str(uuid.uuid4()), branch_a, "programado", "scheduled"))
    db.execute("INSERT INTO notification_inbox VALUES (?,?,?)", (str(uuid.uuid4()), branch_a, 0))
    # other-branch noise must not leak in
    db.execute("INSERT INTO delivery_orders VALUES (?,?,?,?)", (str(uuid.uuid4()), branch_b, "pendiente", 1))
    db.commit()

    svc = OrderBadgeService(db)
    c = svc.get_badge_counts(branch_id=branch_a)  # str UUID, never int()
    assert c["orders_active"] == 2
    assert c["orders_scheduled"] == 1
    assert c["adjustments_pending"] == 1
    assert c["notifications_unread"] == 1


def test_badge_counts_without_notification_inbox_table_do_not_fail():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE delivery_orders (id INTEGER PRIMARY KEY, sucursal_id INTEGER, estado TEXT, adjustment_pending INTEGER DEFAULT 0);
        CREATE TABLE ventas (id INTEGER PRIMARY KEY, sucursal_id INTEGER, estado TEXT, workflow_type TEXT);
        """
    )
    db.execute("INSERT INTO delivery_orders VALUES (1,1,'pendiente',1)")
    db.execute("INSERT INTO ventas VALUES (1,1,'programado','scheduled')")
    db.commit()

    svc = OrderBadgeService(db)
    c = svc.get_badge_counts(branch_id=1)
    assert c["orders_active"] == 1
    assert c["orders_scheduled"] == 1
    assert c["adjustments_pending"] == 1
    assert c["notifications_unread"] == 0
