"""PRC-6 — proyección de costo por evento + facade de lectura + wiring."""

import sqlite3
from decimal import Decimal

import pytest

from backend.application.pricing.event_handlers.product_cost_projection_handler import (
    ProductCostProjectionHandler,
)
from backend.application.pricing.queries.pricing_read_facade import PricingReadFacade
from backend.application.pricing.queries.product_price_query_service import (
    ProductCostQueryService,
)
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_pricing_schema(c)
    c.execute("ALTER TABLE product_cost ADD COLUMN tracked_quantity TEXT")  # migración 151
    c.commit()
    yield c
    c.close()


def _receipt(event_id, *lines, operation_id=None):
    return {"event_id": event_id, "operation_id": operation_id or event_id,
            "lines": [{"product_id": p, "quantity": q, "unit_cost": u} for p, q, u in lines]}


def test_first_receipt_creates_cost(conn):
    h = ProductCostProjectionHandler(conn)
    h.handle(_receipt("e1", ("p1", "10", "60")))
    assert ProductCostQueryService(conn).get_average_cost("p1").amount == Decimal("60")


def test_second_receipt_weighted_average(conn):
    h = ProductCostProjectionHandler(conn)
    h.handle(_receipt("e1", ("p1", "10", "60")))
    h.handle(_receipt("e2", ("p1", "10", "80")))
    assert ProductCostQueryService(conn).get_average_cost("p1").amount == Decimal("70")


def test_idempotent_replay(conn):
    h = ProductCostProjectionHandler(conn)
    ev = _receipt("e1", ("p1", "10", "60"))
    h.handle(ev)
    h.handle(ev)  # mismo event → no recalcula
    assert ProductCostQueryService(conn).get_average_cost("p1").amount == Decimal("60")
    assert conn.execute("SELECT COUNT(*) FROM price_change_log WHERE product_id='p1'"
                        ).fetchone()[0] == 1


def test_bad_line_skipped_not_raised(conn):
    h = ProductCostProjectionHandler(conn)
    h.handle(_receipt("e1", ("p1", "10", "60"), ("p2", "0", "99"), ("", "5", "5")))
    svc = ProductCostQueryService(conn)
    assert svc.get_average_cost("p1").amount == Decimal("60")
    assert svc.get_average_cost("p2") is None


def test_emits_outbox_event(conn):
    ProductCostProjectionHandler(conn).handle(_receipt("e1", ("p1", "10", "60")))
    row = conn.execute("SELECT event_name, entity_id FROM pricing_outbox").fetchone()
    assert row["event_name"] == "PRODUCT_COST_UPDATED" and row["entity_id"] == "p1"


def test_facade_reads_cost(conn):
    ProductCostProjectionHandler(conn).handle(_receipt("e1", ("p1", "10", "60")))
    facade = PricingReadFacade(conn)
    assert facade.unit_cost("p1") == Decimal("60")
    assert facade.average_cost("p1") == Decimal("60")
    assert facade.unit_cost("nope") is None


def test_no_event_id_ignored(conn):
    ProductCostProjectionHandler(conn).handle({"lines": [{"product_id": "p1",
                                              "quantity": "1", "unit_cost": "5"}]})
    assert ProductCostQueryService(conn).get_average_cost("p1") is None


def test_wiring_subscribes_cost_events(conn):
    from backend.application.pricing.integrations.wiring import wire_pricing

    class _Bus:
        def __init__(self):
            self.subs = []
        def subscribe(self, name, handler, priority=0, label=""):
            self.subs.append((name, priority, label))

    bus = _Bus()
    summary = wire_pricing(bus, conn)
    names = {s[0] for s in bus.subs}
    assert "PURCHASE_STOCK_ENTRY_REGISTERED" in names
    assert "PRODUCTION_OUTPUT_COSTED" in names
    assert all(s[1] == 50 for s in bus.subs)  # prioridad ledger/costeo
    assert summary["count"] == 2
