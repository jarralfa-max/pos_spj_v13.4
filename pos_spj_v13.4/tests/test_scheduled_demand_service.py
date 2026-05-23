import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.scheduled_demand_service import ScheduledDemandService


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    return db


def test_register_scheduled_sale_persists_and_emits_event():
    db = _db()
    svc = ScheduledDemandService(db)

    affected = svc.register_scheduled_sale(
        sale_id=11,
        branch_id=2,
        customer_id=3,
        folio="WA-11",
        scheduled_at="2026-05-30 10:00:00",
        items=[{"producto_id": 7, "cantidad": 2.0, "unidad": "kg"}],
    )
    assert affected == 1

    row = db.execute("SELECT * FROM scheduled_demand_events WHERE sale_id=11").fetchone()
    assert row["branch_id"] == 2
    assert row["product_id"] == 7
    assert float(row["quantity"]) == 2.0

    evt = db.execute("SELECT event_type, data_json FROM wa_event_log ORDER BY id DESC LIMIT 1").fetchone()
    assert evt["event_type"] == "FORECAST_DEMAND_UPDATED"
    assert "\"sale_id\": 11" in evt["data_json"]


def test_register_scheduled_sale_is_idempotent_per_sale_product_datetime():
    db = _db()
    svc = ScheduledDemandService(db)
    kwargs = dict(
        sale_id=12,
        branch_id=1,
        customer_id=9,
        folio="WA-12",
        scheduled_at="2026-05-30 11:00:00",
    )
    svc.register_scheduled_sale(items=[{"producto_id": 8, "cantidad": 1.0}], **kwargs)
    svc.register_scheduled_sale(items=[{"producto_id": 8, "cantidad": 1.5}], **kwargs)

    rows = db.execute("SELECT quantity FROM scheduled_demand_events WHERE sale_id=12 AND product_id=8").fetchall()
    assert len(rows) == 1
    assert float(rows[0]["quantity"]) == 1.5
