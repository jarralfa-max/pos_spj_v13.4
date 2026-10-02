"""FASE 6 Compras (2026-09-25): adjudicación → órdenes de compra.

Antes: la adjudicación sólo escribía `purchase_awards` y ahí moría el flujo; y aun
capturando órdenes a mano, la PRIMERA marcaba la solicitud SOURCED y la segunda
(adjudicación dividida) era imposible.

Ahora: una orden por proveedor adjudicado (precio cotizado, cantidad adjudicada),
idempotente por (adjudicación, proveedor) — también en la base, con índice único —
y la solicitud queda PARCIALMENTE o TOTALMENTE abastecida según lo que cubran sus
órdenes.
"""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.application.procurement.permissions import ALL_PURCHASE_PERMISSIONS  # noqa: E402
from backend.infrastructure.db.schema.document_output_schema import (  # noqa: E402
    create_document_numbering_schema,
)
from backend.infrastructure.db.schema.procurement_schema import (  # noqa: E402
    create_procurement_schema,
)
from frontend.desktop.modules.purchasing.dialogs import enterprise_dialogs  # noqa: E402
from frontend.desktop.modules.purchasing.enterprise_routes import (  # noqa: E402
    build_enterprise_presenter,
)
from frontend.desktop.modules.purchasing.pages import enterprise_pages  # noqa: E402
from tests.integration._supplier_cutover import apply_supplier_cutover  # noqa: E402
from tests.integration.procurement._purchase_context import seed_purchase_context  # noqa: E402


class Buyer:
    is_active = True
    user_id = "user-1"
    active_branch_id = "br-1"
    active_warehouse_id = ""      # como la sesión real

    def tiene_permiso(self, code):
        return code in ALL_PURCHASE_PERMISSIONS


class Approver(Buyer):
    user_id = "user-2"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_procurement_schema(c)
    create_document_numbering_schema(c)
    c.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    c.executemany("INSERT INTO proveedores VALUES (?,?,1)",
                  [("s1", "Avícola Norte"), ("s2", "Granja Sur")])
    apply_supplier_cutover(c)
    seed_purchase_context(c)                       # p1 Pollo, p2 Caja; wh-1 de br-1
    c.execute("INSERT INTO warehouses (id, code, name, branch_id) VALUES"
              " ('wh-9','AL9','Otra sucursal','br-9')")
    c.execute("CREATE TABLE sucursales(id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    c.execute("INSERT INTO sucursales VALUES ('br-1','Centro',1)")
    c.execute("CREATE TABLE usuarios_sucursales (usuario_id TEXT, sucursal_id TEXT)")
    c.execute("INSERT INTO usuarios_sucursales VALUES ('user-1','br-1')")
    c.commit()
    yield c
    c.close()


@pytest.fixture
def buyer(conn):
    return build_enterprise_presenter(conn, Buyer())


def _rfq_with_quotes(conn, buyer):
    ok, msg, data = buyer.create_requisition(
        branch_id="br-1", purchase_type="INVENTORY", priority="NORMAL",
        business_reason="reabasto", lines=[{"product_id": "p1", "quantity": "10"},
                                           {"product_id": "p2", "quantity": "5"}])
    assert ok, msg
    rid = data["entity_id"]
    assert buyer.submit_requisition(rid)[0]
    assert build_enterprise_presenter(conn, Approver()).approve_requisition(rid)[0]
    ok, msg, data = buyer.create_rfq_from_requisition(rid, ["s1", "s2"])
    assert ok, msg
    rfq_id = data["entity_id"]
    for supplier, prices in (("s1", ("40", "90")), ("s2", ("45", "80"))):
        ok, msg, _ = buyer.capture_quote(rfq_id=rfq_id, supplier_id=supplier, lines=[
            {"product_id": "p1", "quantity": "10", "unit_price": prices[0]},
            {"product_id": "p2", "quantity": "5", "unit_price": prices[1]}])
        assert ok, msg
    return rid, rfq_id


def _award(buyer, rfq_id, choices):
    """``choices``: {product_id: supplier_id} — la línea ganadora por producto."""
    rows = buyer.quote_comparison(rfq_id)
    lines = [{"quote_line_id": r.quote_line_id, "supplier_id": r.supplier_id,
              "awarded_quantity": r.quantity, "justification": "mejor precio"}
             for r in rows if choices.get(r.product_id) == r.supplier_id]
    ok, msg, _ = buyer.award_quote(award_lines=lines, reason="mejor precio")
    assert ok, msg
    return buyer.award_orders(rfq_id)


def _orders(conn):
    return conn.execute("SELECT supplier_id, document_number FROM purchase_orders"
                        " ORDER BY supplier_id").fetchall()


def _requisition_status(conn, rid):
    return conn.execute("SELECT status FROM purchase_requisitions WHERE id=?",
                        (rid,)).fetchone()[0]


# ── adjudicación dividida → una orden por proveedor ───────────────────────────

def test_split_award_generates_one_order_per_supplier(conn, buyer):
    rid, rfq_id = _rfq_with_quotes(conn, buyer)
    award = _award(buyer, rfq_id, {"p1": "s1", "p2": "s2"})
    assert [s["order_number"] for s in award["suppliers"]] == ["", ""]

    ok, msg, data = buyer.generate_orders_from_award(award["award_id"], "wh-1")
    assert ok, msg
    assert [s for s, _ in _orders(conn)] == ["s1", "s2"]
    # precio COTIZADO del ganador y cantidad adjudicada
    lines = dict(conn.execute(
        "SELECT o.supplier_id, l.unit_price || '@' || l.ordered_quantity"
        " FROM purchase_order_lines l JOIN purchase_orders o ON o.id=l.purchase_order_id"
    ).fetchall())
    assert lines == {"s1": "40@10", "s2": "80@5"}
    # las dos órdenes cubren todo: la solicitud queda abastecida (antes la 2ª fallaba)
    assert _requisition_status(conn, rid) == "SOURCED"
    rows = conn.execute("SELECT source_requisition_id, source_rfq_id, source_award_id"
                        " FROM purchase_orders").fetchall()
    assert all(r == (rid, rfq_id, award["award_id"]) for r in rows)


def test_generating_again_never_duplicates(conn, buyer):
    _rid, rfq_id = _rfq_with_quotes(conn, buyer)
    award = _award(buyer, rfq_id, {"p1": "s1", "p2": "s2"})
    assert buyer.generate_orders_from_award(award["award_id"], "wh-1")[0]
    ok, msg, data = buyer.generate_orders_from_award(award["award_id"], "wh-1")
    assert ok and "ya estaban generadas" in msg
    assert len(_orders(conn)) == 2
    assert all(o["already_registered"] for o in data["orders"])


def test_the_database_refuses_a_second_order_for_the_same_award_and_supplier(conn, buyer):
    _rid, rfq_id = _rfq_with_quotes(conn, buyer)
    award = _award(buyer, rfq_id, {"p1": "s1", "p2": "s1"})
    assert buyer.generate_orders_from_award(award["award_id"], "wh-1")[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO purchase_orders (id, document_number, supplier_id,"
                     " branch_id, warehouse_id, source_award_id, created_at, updated_at)"
                     " SELECT 'dup', 'OC-X', supplier_id, branch_id, warehouse_id,"
                     " source_award_id, created_at, updated_at FROM purchase_orders LIMIT 1")


def test_partial_award_leaves_the_requisition_partially_sourced(conn, buyer):
    rid, rfq_id = _rfq_with_quotes(conn, buyer)
    award = _award(buyer, rfq_id, {"p1": "s1"})            # p2 sin adjudicar
    assert buyer.generate_orders_from_award(award["award_id"], "wh-1")[0]
    assert _requisition_status(conn, rid) == "PARTIALLY_SOURCED"
    # y el resto se puede surtir con OTRA orden (antes: "requiere solicitud aprobada")
    ok, msg, _ = buyer.create_order(
        supplier_id="s2", branch_id="br-1", warehouse_id="wh-1", requisition_id=rid,
        lines=[{"product_id": "p2", "quantity": "5", "unit_price": "80"}])
    assert ok, msg
    assert _requisition_status(conn, rid) == "SOURCED"


def test_a_failed_generation_creates_nothing_and_can_be_retried(conn, buyer):
    _rid, rfq_id = _rfq_with_quotes(conn, buyer)
    award = _award(buyer, rfq_id, {"p1": "s1", "p2": "s2"})
    ok, msg, data = buyer.generate_orders_from_award(award["award_id"], "wh-9")
    assert not ok and data["error_code"] == "WAREHOUSE_NOT_IN_BRANCH"
    assert _orders(conn) == []
    assert buyer.generate_orders_from_award(award["award_id"], "wh-1")[0]
    assert len(_orders(conn)) == 2


# ── pantalla ──────────────────────────────────────────────────────────────────

def test_dialog_shows_suppliers_and_generates_from_the_rfq(app, conn, buyer, monkeypatch):
    _rid, rfq_id = _rfq_with_quotes(conn, buyer)
    _award(buyer, rfq_id, {"p1": "s1", "p2": "s2"})
    seen = {}

    def fake_exec(self):
        seen["rows"] = [[self._table.item(r, c).text() for c in range(4)]
                        for r in range(self._table.rowCount())]
        seen["warehouse"] = self.warehouse_id()
        self.accept()
        return self.result()

    monkeypatch.setattr(enterprise_dialogs.GenerateOrdersDialog, "exec_", fake_exec)
    ok, message = enterprise_pages.open_generate_orders(None, buyer, rfq_id)
    assert ok and "2 orden(es) generada(s)" in message and "OC-" in message
    assert seen["warehouse"] == "wh-1"             # único almacén: preseleccionado
    assert [r[0] for r in seen["rows"]] == ["Avícola Norte", "Granja Sur"]  # nombres
    assert all(r[3] == "Por generar" for r in seen["rows"])
    # una vez generadas, el diálogo ya no ofrece generar
    award = buyer.award_orders(rfq_id)
    dialog = enterprise_dialogs.GenerateOrdersDialog(award=award, warehouse_options=[])
    assert not dialog._ok.isEnabled() and "ya están generadas" in dialog.error_text()


def test_rfq_panel_offers_generate_orders_only_while_some_are_missing(app, conn, buyer):
    from frontend.desktop.modules.purchasing.document_detail import RfqDetailPanel
    _rid, rfq_id = _rfq_with_quotes(conn, buyer)
    panel = RfqDetailPanel(None, buyer.capabilities())
    panel.load_detail(buyer.rfq_detail(rfq_id), buyer.award_orders(rfq_id))
    assert not panel.orders_button.isEnabled()      # sin adjudicar todavía
    award = _award(buyer, rfq_id, {"p1": "s1", "p2": "s2"})
    panel.load_detail(buyer.rfq_detail(rfq_id), award)
    assert panel.orders_button.isEnabled()
    assert "Avícola Norte: orden por generar" in panel._summary.text()
    buyer.generate_orders_from_award(award["award_id"], "wh-1")
    panel.load_detail(buyer.rfq_detail(rfq_id), buyer.award_orders(rfq_id))
    assert not panel.orders_button.isEnabled()
    assert "Avícola Norte: OC-" in panel._summary.text()
    assert "SENT" not in panel._summary.text() and "DRAFT" not in panel._summary.text()


def test_awarding_closes_the_rfq(conn, buyer):
    _rid, rfq_id = _rfq_with_quotes(conn, buyer)
    assert buyer.rfq_detail(rfq_id).status != "CLOSED"
    _award(buyer, rfq_id, {"p1": "s1", "p2": "s2"})
    assert buyer.rfq_detail(rfq_id).status == "CLOSED"     # antes: «Borrador» para siempre


def test_if_one_supplier_fails_no_order_is_left_behind(conn, buyer):
    """Pendiente de la FASE 6: antes la orden de s1 quedaba creada aunque la de s2
    fallara. Ahora es una sola transacción: todas o ninguna, y sin quemar folios."""
    rid, rfq_id = _rfq_with_quotes(conn, buyer)
    award = _award(buyer, rfq_id, {"p1": "s1", "p2": "s2"})
    conn.execute("UPDATE products SET lifecycle_status='INACTIVE' WHERE id='p2'")
    conn.commit()
    ok, msg, data = buyer.generate_orders_from_award(award["award_id"], "wh-1")
    assert not ok and msg.startswith("No se generó ninguna orden")
    assert data["failures"][0]["supplier_id"] == "s2"
    assert _orders(conn) == []
    assert _requisition_status(conn, rid) == "APPROVED"      # la solicitud tampoco cambió
    conn.execute("UPDATE products SET lifecycle_status='ACTIVE' WHERE id='p2'")
    conn.commit()
    assert buyer.generate_orders_from_award(award["award_id"], "wh-1")[0]
    assert [n for _, n in _orders(conn)] == ["OC-%s-000001" % _year(), "OC-%s-000002" % _year()]


def _year():
    from datetime import date
    return date.today().year
