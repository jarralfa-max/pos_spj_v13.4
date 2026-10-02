"""Compras FASE 16 — recibir una orden desde la pantalla, por línea y con la
trazabilidad que el producto exige (§25, §49: por capacidades, no por categoría).

Antes el diálogo recibía por PRODUCTO, en una sola fila, sin lote, caducidad,
peso ni temperatura: desde la FASE 11 el caso de uso exige esos datos según el
perfil de Productos, así que un producto con lote no se podía recibir desde la
pantalla de Órdenes.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication

from frontend.desktop.modules.purchasing.dialogs.enterprise_dialogs import (
    ReceiveOrderDialog,
    ReceiveOrderLineDialog,
)
from tests.integration.procurement.test_invoice_to_payable_chain import (  # noqa: F401
    _presenters,
    conn,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _profiles(**traced):
    def provider(product_id):
        return SimpleNamespace(**traced.get(product_id, {}))
    return provider


def _order(conn):
    compras, gerente = _presenters(conn)
    for p in (compras, gerente):
        p._dispatch = None
    ok, msg, d = compras.create_order(supplier_id="sup-1", branch_id="br-1", warehouse_id="wh-1",
                                      lines=[{"product_id": "p1", "quantity": "10",
                                              "unit_price": "50"},
                                             {"product_id": "p2", "quantity": "4",
                                              "unit_price": "20"}])
    assert ok, msg
    po = d["entity_id"]
    assert gerente.approve_order(po)[0] and compras.send_order(po)[0]
    return compras, po


def test_simple_lines_are_prefilled_and_linked_to_their_order_line(app, conn):
    compras, po = _order(conn)
    detail = compras.order_detail(po)
    dialog = ReceiveOrderDialog(None, order_detail=detail, profile_provider=_profiles())
    assert dialog.problem() is None
    lines = dialog.receipt_lines()
    assert {(ln["purchase_order_line_id"], ln["received_quantity"]) for ln in lines} == {
        (line.id, line.ordered_quantity) for line in detail.lines}
    ok, msg, _ = compras.receive_order(po, receipt_lines=lines)
    assert ok, msg
    assert compras.order_detail(po).status == "RECEIVED"
    assert ReceiveOrderDialog(None, order_detail=compras.order_detail(po)).problem() \
        == "Captura al menos una línea recibida."


def test_a_lot_and_weight_tracked_line_blocks_until_captured(app, conn):
    compras, po = _order(conn)
    detail = compras.order_detail(po)
    dialog = ReceiveOrderDialog(None, order_detail=detail, profile_provider=_profiles(
        p1={"lot_controlled": True, "catch_weight": True}))
    captures = {c["product_id"]: c for c in dialog._captures}
    assert captures["p1"]["received"] == 0          # no se prellena: exige datos
    captures["p1"].update(received="10", accepted="9", rejection_reason="golpeado")
    assert "falta lote, peso real" in dialog.problem()

    line_dialog = ReceiveOrderLineDialog(None, capture=captures["p1"])
    assert "requiere el peso neto" in line_dialog.problem()
    line_dialog._trace._weight.set_decimal("25.4")
    line_dialog._trace._lot.setText("L-77")
    assert line_dialog.problem() is None
    captures["p1"].update(line_dialog.values())
    assert dialog.problem() is None

    (traced,) = [ln for ln in dialog.receipt_lines() if ln["product_id"] == "p1"]
    assert (traced["lot"], Decimal(traced["net_weight"]), Decimal(traced["accepted_quantity"]),
            traced["rejection_reason"]) == ("L-77", Decimal("25.4"), Decimal("9"), "golpeado")
    ok, msg, _ = compras.receive_order(po, receipt_lines=dialog.receipt_lines())
    assert ok, msg
    row = conn.execute("SELECT lot, net_weight, accepted_quantity, purchase_order_line_id"
                       " FROM goods_receipt_lines WHERE product_id='p1'").fetchone()
    assert (row[0], Decimal(row[1]), Decimal(row[2]), row[3]) == (
        "L-77", Decimal("25.4"), Decimal("9"), captures["p1"]["line_id"])
