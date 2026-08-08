"""PUR-5 UI — the direct-purchase page builds, wires to the presenter, and drives
the full flow (create → authorize → confirm → reverse) without touching SQL.

Runs headless (QT_QPA_PLATFORM=offscreen). Skipped if PyQt5 is unavailable.
"""

import os
import sqlite3
from decimal import Decimal

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

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
from backend.application.procurement.permissions import ALL_PURCHASE_PERMISSIONS  # noqa: E402


class Session:
    is_active = True
    user_id = "user-1"
    active_branch_id = "br-1"
    active_warehouse_id = "wh-1"

    def tiene_permiso(self, code):
        return code in ALL_PURCHASE_PERMISSIONS


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_procurement_schema(c)
    c.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    c.execute("INSERT INTO proveedores VALUES ('sup-1','Proveedor Uno',1)")
    yield c
    c.close()


def test_page_builds_and_lists(app, conn):
    from frontend.desktop.modules.purchasing.direct_purchase_view import (
        DirectPurchaseCreateView, DirectPurchaseHistoryView,
    )

    presenter = build_direct_purchase_presenter(conn, Session())
    create = DirectPurchaseCreateView(presenter)
    history = DirectPurchaseHistoryView(presenter)
    history.ensure_loaded()
    assert create is not None and history is not None


def test_presenter_totals_are_decimal_backed(app, conn):
    presenter = build_direct_purchase_presenter(conn, Session())
    lines = [CartLineVM("p1", "Pollo", Decimal("3"), Decimal("100"), tax=Decimal("48")),
             CartLineVM("p2", "Caja", Decimal("2"), Decimal("50"))]
    totals = presenter.totals(lines)
    assert "448" in totals["total"]  # 300 + 100 + 48


def test_presenter_full_flow(app, conn):
    presenter = build_direct_purchase_presenter(conn, Session())
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


def test_purchases_table_shows_supplier_name_not_uuid(app, conn):
    presenter = build_direct_purchase_presenter(conn, Session())
    lines = [CartLineVM("p1", "Pollo", Decimal("3"), Decimal("100"))]
    ok, _msg, _data = presenter.create(
        supplier_id="sup-1", lines=lines, mode="DIRECT_WITH_IMMEDIATE_RECEIPT",
        payment_condition="IMMEDIATE_PAYMENT", branch_id="br-1", warehouse_id="wh-1")
    assert ok
    model = presenter.purchases()
    assert model.total == 1
    assert model.rows[0][1] == "Proveedor Uno"
    assert "sup-1" not in model.rows[0][1]


def test_presenter_blocks_pos_cash(app, conn):
    presenter = build_direct_purchase_presenter(conn, Session())
    lines = [CartLineVM("p1", "x", Decimal("1"), Decimal("10"))]
    _ok, _m, data = presenter.create(
        supplier_id="sup-1", lines=lines, mode="DIRECT_WITH_IMMEDIATE_RECEIPT",
        payment_condition="IMMEDIATE_PAYMENT", branch_id="br-1", warehouse_id="wh-1")
    ok, msg, _ = presenter.confirm(data["entity_id"], "POS_CASH")
    assert not ok and "caja" in msg.lower()
