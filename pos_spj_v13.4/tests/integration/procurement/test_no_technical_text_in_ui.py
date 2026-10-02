"""Compras FASE 15 (§19, §20, §41 pruebas 8 y 9) — la pantalla nunca muestra
un UUID ni un estado técnico sin traducir.

Se generan documentos en muchos estados (solicitud en borrador, pendiente y
abastecida; RFQ adjudicada; órdenes en borrador, recibidas parcialmente y
completas; factura conciliada y con diferencia; compra directa con recepción
pendiente y recibida; recepción con rechazo) y se recorren TODAS las páginas
principales del módulo, seleccionando filas para que también se pinten los
paneles de detalle. Cualquier texto visible con un UUID, un CÓDIGO_TÉCNICO o
un error de Python hace fallar la prueba.

Medido el 2026-09-30 en una copia de la base real antes de corregir: la
página de Recepciones mostraba «'EnterprisePurchasingPresenter' object has no
attribute 'receipts'», el detalle de solicitudes «DRAFT»/«PENDING_APPROVAL»/
«SOURCED», prioridad «URGENT», naturaleza «INVENTORY», y los documentos
relacionados de la orden «CANCELLED»/«MATCHED».
"""

import re

import pytest
from PyQt5.QtWidgets import (
    QAbstractButton, QApplication, QComboBox, QLabel, QTableWidget, QTabWidget, QWidget,
)

from backend.application.procurement.use_cases.direct_purchase_use_cases import (
    ReceiveDirectPurchaseUseCase,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import CartLineVM
from frontend.desktop.modules.purchasing.enterprise_routes import (
    create_enterprise_purchasing_view,
)
from frontend.desktop.modules.purchasing.navigation import IMPLEMENTED_PURCHASING_ROUTES
from tests.integration.procurement.test_invoice_to_payable_chain import (  # noqa: F401
    _Session,
    _presenters,
    conn,
)

UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
CODE = re.compile(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b")
STATUS_WORDS = {
    "DRAFT", "SENT", "CLOSED", "CONFIRMED", "RECEIVED", "APPROVED", "PENDING", "OPEN",
    "CAPTURED", "MATCHED", "SEALED", "DISPATCHED", "CANCELLED", "REVERSED", "AVAILABLE",
    "INVENTORY", "EXPENSE", "ASSET", "SERVICE", "ACKNOWLEDGED", "SUBMITTED", "REJECTED",
    "SOURCED", "BLOCKED", "POSTED", "SETTLED", "COMPLETED", "HIGH", "LOW", "URGENT",
    "NORMAL", "PO",
}
PYTHON_ERRORS = re.compile(r"has no attribute|Traceback|NoneType|object is not")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _seed(conn):
    compras, gerente = _presenters(conn)
    for p in (compras, gerente):
        p._dispatch = None
    # solicitudes: borrador, pendiente, y una abastecida por RFQ → adjudicación → OC
    compras.create_requisition(branch_id="br-1", purchase_type="INVENTORY", priority="NORMAL",
                               business_reason="borrador", lines=[{"product_id": "p1",
                                                                   "quantity": "2"}])
    ok, _, d = compras.create_requisition(
        branch_id="br-1", purchase_type="INVENTORY", priority="URGENT",
        business_reason="pendiente", lines=[{"product_id": "p2", "quantity": "3"}])
    compras.submit_requisition(d["entity_id"])
    ok, _, d = compras.create_requisition(
        branch_id="br-1", purchase_type="INVENTORY", priority="HIGH",
        business_reason="reabasto", lines=[{"product_id": "p1", "quantity": "5"}])
    req = d["entity_id"]
    compras.submit_requisition(req)
    gerente.approve_requisition(req)
    ok, msg, d = compras.create_rfq_from_requisition(req, ["sup-1"])
    assert ok, msg
    rfq = d["entity_id"]
    compras.capture_quote(rfq_id=rfq, supplier_id="sup-1", lines=[
        {"product_id": "p1", "quantity": "5", "unit_price": "40"}])
    rows = compras.quote_comparison(rfq)
    ok, msg, award = compras.award_quote(award_lines=[{
        "quote_line_id": r.quote_line_id, "supplier_id": r.supplier_id,
        "awarded_quantity": r.quantity, "justification": "precio"} for r in rows],
        reason="precio")
    assert ok, msg
    assert compras.generate_orders_from_award(
        award.get("entity_id") or award.get("award_id"), "wh-1")[0]
    # orden con descuento e IVA, recibida en dos partes, con rechazo y facturas
    ok, msg, d = compras.create_order(supplier_id="sup-1", branch_id="br-1", warehouse_id="wh-1",
                                      lines=[{"product_id": "p1", "quantity": "10",
                                              "unit_price": "50", "discount": "10",
                                              "tax": "80"}])
    assert ok, msg
    po = d["entity_id"]
    gerente.approve_order(po)
    compras.send_order(po)
    line = compras.order_detail(po).lines[0].id
    assert compras.receive_order(po, receipt_lines=[{
        "product_id": "p1", "purchase_order_line_id": line, "received_quantity": "6",
        "accepted_quantity": "5", "discrepancy_type": "QUALITY_FAILURE",
        "discrepancy_reason": "golpeado"}])[0]
    for number, price in (("A-1", "49"), ("A-2", "60")):
        ok, msg, inv = compras.capture_invoice(
            supplier_id="sup-1", invoice_number=number, total=str(2 * float(price) + 16),
            purchase_order_id=po, lines=[{"product_id": "p1", "invoiced_quantity": "2",
                                          "unit_price": price, "tax": "16",
                                          "purchase_order_line_id": line}])
        assert ok, msg
        gerente.match_invoice(inv["entity_id"])
    # orden en borrador
    compras.create_order(supplier_id="sup-1", branch_id="br-1", warehouse_id="wh-1",
                         lines=[{"product_id": "p2", "quantity": "1", "unit_price": "9"}])
    # compra directa con recepción pendiente, recibida después
    from frontend.desktop.modules.purchasing.direct_purchase_routes import (
        build_direct_purchase_presenter,
    )
    direct = build_direct_purchase_presenter(conn, _Session("comprador"))
    direct._dispatch = None
    from decimal import Decimal
    ok, msg, d = direct.create(supplier_id="sup-1", mode="DIRECT_WITH_PENDING_RECEIPT",
                               payment_condition="SUPPLIER_CREDIT", branch_id="br-1",
                               warehouse_id="wh-1",
                               lines=[CartLineVM("p1", "Pollo", Decimal("3"), Decimal("45"))])
    assert ok, msg
    assert direct.confirm(d["entity_id"], None)[0]
    assert direct.receive(d["entity_id"])[0]
    direct.create(supplier_id="sup-1", mode="DIRECT_WITH_PENDING_RECEIPT",
                  payment_condition="SUPPLIER_CREDIT", branch_id="br-1", warehouse_id="wh-1",
                  lines=[CartLineVM("p2", "Caja", Decimal("1"), Decimal("12"))])
    assert ReceiveDirectPurchaseUseCase  # el caso de uso existe (FASE 14)


def _visible_texts(root: QWidget) -> list[str]:
    texts = []
    for widget in root.findChildren(QWidget):
        if not widget.isVisibleTo(root):
            continue
        if isinstance(widget, (QLabel, QAbstractButton)):
            texts.append(widget.text())
        elif isinstance(widget, QTableWidget):
            texts += [widget.item(r, c).text() for r in range(widget.rowCount())
                      for c in range(widget.columnCount()) if widget.item(r, c)]
            texts += [widget.horizontalHeaderItem(c).text() for c in range(widget.columnCount())
                      if widget.horizontalHeaderItem(c)]
        elif isinstance(widget, QComboBox):
            texts += [widget.itemText(i) for i in range(widget.count())]
    return [t for t in texts if t]


def _problems(text: str) -> list[str]:
    found = UUID.findall(text) + CODE.findall(text)
    found += [w for w in re.findall(r"\b[A-Z_]{2,}\b", text) if w in STATUS_WORDS]
    if PYTHON_ERRORS.search(text):
        found.append("error de Python")
    return found


def test_no_uuid_nor_technical_status_on_any_main_page(app, conn):
    _seed(conn)

    class Container:
        db = conn
        session = _Session("comprador")

    view = create_enterprise_purchasing_view(Container())
    view.resize(1366, 768)
    view.show()
    view.refresh_permissions()
    app.processEvents()
    offenders: dict[str, set] = {}
    visited = 0
    for route in IMPLEMENTED_PURCHASING_ROUTES:
        view.navigate_to(route.key)
        app.processEvents()
        page = view.content.currentWidget()
        if hasattr(page, "ensure_loaded"):
            page.ensure_loaded()
        app.processEvents()
        visited += 1
        snapshots = [_visible_texts(page)]
        for tabs in page.findChildren(QTabWidget):
            for index in range(tabs.count()):
                tabs.setCurrentIndex(index)
                app.processEvents()
                snapshots.append(_visible_texts(page))
        for table in page.findChildren(QTableWidget):
            if not table.isVisibleTo(page):
                continue
            for row in range(min(table.rowCount(), 6)):
                table.selectRow(row)
                app.processEvents()
                snapshots.append(_visible_texts(page))
        for texts in snapshots:
            for text in texts:
                found = _problems(text)
                if found:
                    offenders.setdefault(f"{route.label}: {text[:90]}", set()).update(found)
    view.close()
    assert visited == len(IMPLEMENTED_PURCHASING_ROUTES)
    assert not offenders, "\n".join(f"{k} -> {sorted(v)}" for k, v in offenders.items())


def test_receipts_page_lists_receipts_with_names(app, conn):
    _seed(conn)
    compras, _ = _presenters(conn)
    rows = compras.receipts()
    assert rows and all(not UUID.search(str(v)) for row in rows
                        for k, v in row.items() if k != "id")
    detail = compras.receipt_detail(rows[-1]["id"])
    assert detail["lines"][0]["product"] == "P1 · Pollo"
    assert detail["warehouse"] == "ALM · Almacén"
    assert {d["type"] for d in detail["differences"]} <= {"Rechazo de calidad", "Faltante",
                                                          "Excedente"}
