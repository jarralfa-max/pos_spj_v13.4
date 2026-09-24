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

from backend.infrastructure.db.schema.document_output_schema import (  # noqa: E402
    create_document_numbering_schema,
)
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
from tests.integration._supplier_cutover import apply_supplier_cutover
from tests.integration.procurement._purchase_context import seed_purchase_context


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
    create_document_numbering_schema(c)
    c.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    c.execute("INSERT INTO proveedores VALUES ('sup-1','Proveedor Uno',1)")
    apply_supplier_cutover(c)
    # Producto activo, almacén de br-1 y Finanzas como en la base real: sin esto
    # las pruebas pasaban precisamente porque no se comprobaba nada de ello.
    seed_purchase_context(c)
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
    # Transferencia: se asienta contra la cuenta de Banco. Antes esta prueba
    # pagaba de CAJA CHICA, que no tiene cuenta en la instalación y por tanto
    # no se asentaba — y aun así se confirmaba.
    ok, _m, cdata = presenter.confirm(dp_id, "BANK_TRANSFER")
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



# ── lo que la compra rápida NO debe dejar confirmar (medido 2026-09-18) ──────

def _crear(presenter, *, lines=None, warehouse_id="wh-1", branch_id="br-1"):
    return presenter.create(
        supplier_id="sup-1",
        lines=lines or [CartLineVM("p1", "Pollo", Decimal("3"), Decimal("100"))],
        mode="DIRECT_WITH_IMMEDIATE_RECEIPT", payment_condition="IMMEDIATE_PAYMENT",
        branch_id=branch_id, warehouse_id=warehouse_id)


def test_a_payment_that_cannot_be_booked_is_not_confirmed(app, conn):
    """EL HUECO FINANCIERO. La instalación no tiene cuenta de caja chica: pagar
    de ahí se confirmaba, la mercancía entraba y el dinero salía SIN asiento
    (el puente contable sólo dejaba una advertencia). CLAUDE.md §11."""
    presenter = build_direct_purchase_presenter(conn, Session())
    ok, msg, data = _crear(presenter)
    assert ok, msg
    ok, msg, _ = presenter.confirm(data["entity_id"], "PETTY_CASH")
    assert not ok and "PETTY_CASH" in msg
    estado = conn.execute("SELECT status FROM direct_purchases WHERE id=?",
                          (data["entity_id"],)).fetchone()[0]
    assert estado != "RECEIVED"


def test_the_screen_only_offers_bookable_payment_sources(app, conn):
    """Ofrecer una fuente para que la confirmación la rechace después sería
    otra forma del mismo problema."""
    presenter = build_direct_purchase_presenter(conn, Session())
    assert [k for k, _ in presenter.payment_source_options()] == [
        "BANK_TRANSFER", "MERCADO_PAGO"]


def test_an_inactive_product_is_refused(app, conn):
    conn.execute("UPDATE products SET lifecycle_status='UNDER_REVIEW' WHERE id='p1'")
    conn.commit()
    ok, msg, _ = _crear(build_direct_purchase_presenter(conn, Session()))
    assert not ok and "no está activo" in msg


def test_a_product_not_enabled_for_purchase_is_refused(app, conn):
    conn.execute("UPDATE products SET purchasable=0 WHERE id='p1'")
    conn.commit()
    ok, msg, _ = _crear(build_direct_purchase_presenter(conn, Session()))
    assert not ok and "habilitado para compra" in msg


def test_a_warehouse_of_another_branch_is_refused(app, conn):
    conn.execute("INSERT INTO warehouses (id, code, name, branch_id)"
                 " VALUES ('wh-otra','OTR','Otra','br-2')")
    conn.commit()
    ok, msg, _ = _crear(build_direct_purchase_presenter(conn, Session()),
                        warehouse_id="wh-otra")
    assert not ok and "no pertenece a la sucursal" in msg


def test_a_zero_cost_line_is_refused(app, conn):
    """Decisión del usuario: el costo debe ser mayor a cero."""
    ok, msg, _ = _crear(build_direct_purchase_presenter(conn, Session()),
                        lines=[CartLineVM("p1", "Pollo", Decimal("3"), Decimal("0"))])
    assert not ok and "mayor a cero" in msg


def test_confirming_revalidates_what_changed_since_the_draft(app, conn):
    """Entre el borrador y la confirmación el producto pudo retirarse."""
    presenter = build_direct_purchase_presenter(conn, Session())
    ok, msg, data = _crear(presenter)
    assert ok, msg
    conn.execute("UPDATE products SET lifecycle_status='RETIRED' WHERE id='p1'")
    conn.commit()
    ok, msg, _ = presenter.confirm(data["entity_id"], "BANK_TRANSFER")
    assert not ok and "no está activo" in msg


def test_a_bookable_payment_leaves_its_journal_entry(app, conn):
    """La otra cara: lo que sí se confirma, sí se asienta.

    Con un bus LOCAL y el mismo cableado que el arranque (`wire_procurement` +
    `wire_procurement_downstream_bridges`): el bus de la app es global y
    cablearlo aquí dejaría suscriptores atados a una conexión ya cerrada para
    el resto de las pruebas.
    """
    from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
        dispatch_procurement_outbox,
    )
    from backend.application.procurement.integrations.wiring import wire_procurement
    from backend.bootstrap.wiring.event_wiring import wire_procurement_downstream_bridges
    from backend.shared.events.application_bus import ApplicationEventBus

    presenter = build_direct_purchase_presenter(conn, Session())
    presenter._dispatch = None   # el despacho lo hace la prueba, al bus local
    ok, msg, data = _crear(presenter)
    assert ok, msg
    ok, msg, _ = presenter.confirm(data["entity_id"], "BANK_TRANSFER")
    assert ok, msg
    bus = ApplicationEventBus()
    wire_procurement(bus, conn)
    wire_procurement_downstream_bridges(bus, conn)
    dispatch_procurement_outbox(conn, bus)
    assert conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 1
