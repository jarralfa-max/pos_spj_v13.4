"""PUR-5 UI — the direct-purchase page builds, wires to the presenter, and drives
the full flow (create → authorize → confirm → reverse) without touching SQL.

Runs headless (QT_QPA_PLATFORM=offscreen). Skipped if PyQt5 is unavailable.
"""

import os
import sqlite3
from decimal import Decimal

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.infrastructure.db.schema.procurement_schema import (  # noqa: E402
    create_procurement_schema,
)
from frontend.desktop.modules.purchasing.direct_purchase_routes import (  # noqa: E402
    build_direct_purchase_presenter,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import (  # noqa: E402
    CartLineVM,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_procurement_schema(c)
    yield c
    c.close()


def test_page_builds_and_lists(app, conn):
    from frontend.desktop.modules.purchasing.direct_purchase_view import DirectPurchaseView

    presenter = build_direct_purchase_presenter(conn)
    view = DirectPurchaseView(presenter)
    view.ensure_loaded()  # empty state, no crash
    assert view is not None


def test_presenter_totals_are_decimal_backed(app, conn):
    presenter = build_direct_purchase_presenter(conn)
    lines = [CartLineVM("p1", "Pollo", Decimal("3"), Decimal("100"), tax=Decimal("48")),
             CartLineVM("p2", "Caja", Decimal("2"), Decimal("50"))]
    totals = presenter.totals(lines)
    assert "448" in totals["total"]  # 300 + 100 + 48


def test_presenter_full_flow(app, conn):
    presenter = build_direct_purchase_presenter(conn)
    lines = [CartLineVM("p1", "Pollo", Decimal("3"), Decimal("100"), tax=Decimal("48"))]
    ok, _msg, data = presenter.create(
        supplier_id="sup-1", lines=lines, mode="DIRECT_WITH_IMMEDIATE_RECEIPT",
        payment_condition="IMMEDIATE_PAYMENT", branch_id="br-1", warehouse_id="wh-1")
    assert ok
    dp_id = data["entity_id"]
    ok, _m, cdata = presenter.confirm(dp_id, "PETTY_CASH")
    assert ok and cdata["status"] == "RECEIVED"
    ok, _m, rdata = presenter.reverse(dp_id, "devolución")
    assert ok and rdata["status"] == "REVERSED"


def test_presenter_blocks_pos_cash(app, conn):
    presenter = build_direct_purchase_presenter(conn)
    lines = [CartLineVM("p1", "x", Decimal("1"), Decimal("10"))]
    _ok, _m, data = presenter.create(
        supplier_id="sup-1", lines=lines, mode="DIRECT_WITH_IMMEDIATE_RECEIPT",
        payment_condition="IMMEDIATE_PAYMENT", branch_id="br-1", warehouse_id="wh-1")
    ok, msg, _ = presenter.confirm(data["entity_id"], "POS_CASH")
    assert not ok and "caja" in msg.lower()
