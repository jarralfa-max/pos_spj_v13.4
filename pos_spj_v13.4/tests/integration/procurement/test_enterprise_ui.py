"""PUR-12 UI — the enterprise procurement view (dashboard + requisitions + orders
+ invoices) builds, wires to the presenter, and drives flows without SQL.

Runs headless (QT_QPA_PLATFORM=offscreen). Skipped if PyQt5 is unavailable.
"""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

from PyQt5.QtWidgets import QApplication, QAbstractButton  # noqa: E402

from backend.application.procurement.queries.procurement_analytics_service import (  # noqa: E402
    ProcurementAnalyticsService,
)
from backend.infrastructure.db.schema.procurement_schema import (  # noqa: E402
    create_procurement_schema,
)
from frontend.desktop.modules.purchasing.enterprise_routes import (  # noqa: E402
    build_enterprise_presenter,
)
from backend.application.procurement.permissions import ALL_PURCHASE_PERMISSIONS  # noqa: E402


class Session:
    is_active = True
    user_id = "user-1"
    active_branch_id = "br-1"
    active_warehouse_id = "wh-1"
    nombre_completo = "Comprador de prueba"

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
    c.execute("INSERT INTO proveedores VALUES ('s1','Proveedor Uno',1)")
    c.execute("CREATE TABLE sucursales(id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    c.execute("INSERT INTO sucursales VALUES ('br-1','Sucursal Centro',1)")
    yield c
    c.close()


def test_enterprise_view_builds(app, conn):
    from frontend.desktop.modules.purchasing.enterprise_routes import (
        create_enterprise_purchasing_view,
    )

    container = type("Container", (), {"db": conn, "session": Session()})()
    view = create_enterprise_purchasing_view(container)
    view.ensure_loaded()  # dashboard tab renders (empty), no crash
    assert view is not None


def test_sidebar_routes_and_dashboard_actions_follow_capabilities(app, conn):
    from frontend.desktop.modules.purchasing.enterprise_routes import (
        create_enterprise_purchasing_view,
    )
    from backend.application.procurement.permissions import PurchasePermissions

    class RestrictedSession(Session):
        def tiene_permiso(self, code):
            return code in {
                PurchasePermissions.VIEW,
                PurchasePermissions.REQUISITION_VIEW,
                PurchasePermissions.REQUISITION_CREATE,
            }

    container = type("Container", (), {"db": conn, "session": RestrictedSession()})()
    view = create_enterprise_purchasing_view(container)
    labels = [view.sidebar.item(row).text() for row in range(view.sidebar.count())]
    buttons = [button.text() for button in view.findChildren(QAbstractButton)]

    assert "Solicitudes" in labels
    assert "Órdenes de compra" not in labels
    assert "Compra directa" not in labels
    assert "Nueva solicitud" in buttons
    assert "Nueva orden de compra" not in buttons
    assert all(unfinished not in labels for unfinished in (
        "Cotizaciones", "Adjudicaciones", "Políticas y tolerancias"))

    pr_stage = next(button for button in view.findChildren(QAbstractButton)
                    if button.text() == "PR")
    pr_stage.click()
    app.processEvents()
    assert view.sidebar.currentItem().text().startswith("Solicitudes")


def test_requisition_flow_through_presenter(app, conn):
    presenter = build_enterprise_presenter(conn, Session())
    ok, _msg, data = presenter.create_requisition(
        branch_id="br-1", purchase_type="INVENTORY", priority="NORMAL",
        business_reason="reabasto", lines=[{"product_id": "p1", "quantity": "10"}])
    assert ok
    rid = data["entity_id"]
    ok, _m, _ = presenter.submit_requisition(rid)
    assert ok
    # requester cannot self-approve (segregation enforced in the use case)
    ok, _m, _ = presenter.approve_requisition(rid, approve=True)
    assert not ok  # actor == requester (segregation of duties)
    model = presenter.requisitions()
    assert model.total == 1
    # the "Sucursal" column shows the real branch name, never a raw id/UUID
    assert model.rows[0][1] == "Sucursal Centro"
    assert "br-1" not in model.rows[0][1]


def test_order_create_and_list(app, conn):
    presenter = build_enterprise_presenter(conn, Session())
    ok, _m, data = presenter.create_order(
        supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "quantity": "10", "unit_price": "100"}])
    assert ok and data["total"] == "1000.00"
    model = presenter.orders()
    assert model.total == 1
    # the "Proveedor" column shows the real supplier name, never a raw UUID
    assert model.rows[0][1] == "Proveedor Uno"
    assert "s1" not in model.rows[0][1]


def test_purchase_history_shows_supplier_name_not_uuid(app, conn):
    class OtherSession(Session):
        user_id = "user-2"

    presenter = build_enterprise_presenter(conn, Session())
    approver = build_enterprise_presenter(conn, OtherSession())
    ok, _m, data = presenter.create_order(
        supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "quantity": "10", "unit_price": "100"}])
    assert ok
    order_id = data["entity_id"]
    assert approver.approve_order(order_id)[0]
    assert approver.send_order(order_id)[0]
    ok, msg, _ = approver.receive_order(order_id, receipt_lines=[
        {"product_id": "p1", "received_quantity": "10", "accepted_quantity": "10"}])
    assert ok, msg
    model = presenter.purchase_history()
    assert model.total == 1
    assert model.rows[0][1] == "Proveedor Uno"


def test_invoices_table_shows_supplier_name_not_uuid(app, conn):
    class OtherSession(Session):
        user_id = "user-2"

    presenter = build_enterprise_presenter(conn, Session())
    approver = build_enterprise_presenter(conn, OtherSession())
    ok, _m, data = presenter.create_order(
        supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "quantity": "10", "unit_price": "100"}])
    assert ok
    order_id = data["entity_id"]
    assert approver.approve_order(order_id)[0]
    assert approver.send_order(order_id)[0]
    assert approver.receive_order(order_id, receipt_lines=[
        {"product_id": "p1", "received_quantity": "10", "accepted_quantity": "10"}])[0]
    line_id = conn.execute(
        "SELECT id FROM purchase_order_lines WHERE purchase_order_id=?", (order_id,)
    ).fetchone()[0]
    ok, msg, _ = presenter.capture_invoice(
        supplier_id="s1", invoice_number="A-100", total="1000", purchase_order_id=order_id,
        lines=[{"product_id": "p1", "invoiced_quantity": "10", "unit_price": "100",
                "purchase_order_line_id": line_id}])
    assert ok, msg
    model = presenter.invoices()
    assert model.total == 1
    assert model.rows[0][1] == "Proveedor Uno"


def _approved_requisition(conn, presenter):
    ok, _msg, data = presenter.create_requisition(
        branch_id="br-1", purchase_type="INVENTORY", priority="NORMAL",
        business_reason="reabasto", lines=[{"product_id": "p1", "quantity": "10"}])
    assert ok
    rid = data["entity_id"]
    assert presenter.submit_requisition(rid)[0]

    class Approver(Session):
        user_id = "approver-1"

    from frontend.desktop.modules.purchasing.enterprise_routes import (
        build_enterprise_presenter,
    )
    approver_presenter = build_enterprise_presenter(conn, Approver())
    assert approver_presenter.approve_requisition(rid, approve=True)[0]
    return rid


# ── FASE 2 "Crear puertos": requisition_detail() existed nowhere before this;
# the UI called it (RequisitionsPage, "Crear orden", "Crear RFQ", "Compra
# directa") but it always raised AttributeError before reaching any of the
# code below — these flows were entirely non-functional.
def test_requisition_detail_returns_a_usable_dto(app, conn):
    presenter = build_enterprise_presenter(conn, Session())
    rid = _approved_requisition(conn, presenter)

    detail = presenter.requisition_detail(rid)

    assert detail.id == rid
    assert detail.status == "APPROVED"
    assert detail.branch_id == "br-1"
    assert len(detail.lines) == 1
    assert detail.lines[0].product_id == "p1"


def test_order_form_dialog_builds_from_requisition_detail_without_crashing(app, conn):
    from frontend.desktop.modules.purchasing.dialogs.enterprise_dialogs import (
        OrderFormDialog,
    )

    presenter = build_enterprise_presenter(conn, Session())
    rid = _approved_requisition(conn, presenter)
    detail = presenter.requisition_detail(rid)

    dialog = OrderFormDialog(
        source_requisition=detail, branch_id=presenter.default_branch(),
        warehouse_id=presenter.default_warehouse(),
        supplier_provider=presenter.supplier_options,
        product_provider=presenter.product_options)

    values = dialog.values()
    assert values["branch_id"] == "br-1"
    assert values["lines"] == [{
        "product_id": "p1", "quantity": "10", "purchase_nature": "INVENTORY",
        "unit_price": "0"}]


def test_direct_purchase_create_page_starts_from_requisition_detail(app, conn):
    from frontend.desktop.modules.purchasing.direct_purchase_routes import (
        build_direct_purchase_presenter,
    )
    from frontend.desktop.modules.purchasing.pages.direct_purchase_create_page import (
        DirectPurchaseCreatePage,
    )

    presenter = build_enterprise_presenter(conn, Session())
    rid = _approved_requisition(conn, presenter)
    detail = presenter.requisition_detail(rid)

    direct_presenter = build_direct_purchase_presenter(conn, Session())
    page = DirectPurchaseCreatePage(direct_presenter)
    page.start_from_requisition(detail)

    assert page._source_requisition_id == rid
    assert len(page._cart) == 1
    assert page._cart[0].product_id == "p1"


def test_add_cart_line_dialog_requires_a_catalog_selection_not_free_text(app, conn):
    """The product field is EntitySearchInput now: line() must be None until a
    real catalog product is selected — typing a raw id/code is not enough."""
    from frontend.desktop.modules.purchasing.dialogs.direct_purchase_dialogs import (
        AddCartLineDialog,
    )
    from frontend.desktop.components.search_selector import SearchOption

    def provider(query):
        return [SearchOption(id="prod-uuid-1", label="Pollo entero", subtitle="COD-1")] \
            if "poll" in query.lower() else []

    dialog = AddCartLineDialog(product_provider=provider)
    dialog._quantity.set_decimal("2")
    dialog._unit_cost.set_decimal("50")
    # typing text into the search box alone never selects a product
    assert dialog.line() is None

    dialog._product.set_selected_label("prod-uuid-1", "Pollo entero")
    line = dialog.line()
    assert line is not None
    assert line.product_id == "prod-uuid-1"
    assert line.description == "Pollo entero"  # resolved label, never a raw id


def test_add_cart_line_dialog_prefill_resolves_scanned_code_via_catalog(app, conn):
    from frontend.desktop.modules.purchasing.dialogs.direct_purchase_dialogs import (
        AddCartLineDialog,
    )
    from frontend.desktop.components.search_selector import SearchOption

    def provider(query):
        return [SearchOption(id="prod-uuid-1", label="Pollo entero", subtitle="COD-1")] \
            if query == "COD-1" else []

    dialog = AddCartLineDialog(product_provider=provider)
    dialog.prefill_product("COD-1")
    assert dialog._product.selected_id() == "prod-uuid-1"

    # an unresolvable scanned code never invents a selection
    dialog2 = AddCartLineDialog(product_provider=provider)
    dialog2.prefill_product("UNKNOWN-CODE")
    assert dialog2._product.selected_id() is None


# ── FASE 3 (acotada): costo de referencia visible al capturar línea ──────────
def test_add_cart_line_dialog_shows_reference_cost_once_product_and_cost_are_set(app, conn):
    from frontend.desktop.modules.purchasing.dialogs.direct_purchase_dialogs import (
        AddCartLineDialog,
    )
    from frontend.desktop.components.search_selector import SearchOption

    def provider(_query):
        return [SearchOption(id="p1", label="Pollo entero", subtitle="COD-1")]

    def cost_variance(product_id, captured_cost):
        assert product_id == "p1" and captured_cost == 125
        return {"label": "▲ SUBIÓ 25.0%", "is_significant": True}

    dialog = AddCartLineDialog(product_provider=provider, cost_variance=cost_variance)
    assert dialog._cost_hint.text() == ""  # nothing selected yet — no invented hint

    dialog._product.set_selected_label("p1", "Pollo entero")
    dialog._unit_cost.set_decimal("125")
    assert "▲ SUBIÓ 25.0%" in dialog._cost_hint.text()


def test_supplier_and_invoice_document_options_do_not_crash(app, conn):
    presenter = build_enterprise_presenter(conn, Session())
    assert presenter.supplier_options("Proveedor") != []
    assert presenter.invoice_document_options("") == []  # no billable docs yet
    assert presenter.invoice_document_profile("missing-id") == {}


# ── FASE 3 (acotada): conversión de unidades en líneas de Órdenes ────────────
def test_order_form_dialog_captures_conversion_factor(app, conn):
    from frontend.desktop.modules.purchasing.dialogs.enterprise_dialogs import (
        OrderFormDialog,
    )
    from frontend.desktop.components.search_selector import SearchOption

    def products(_query):
        return [SearchOption(id="p1", label="Pollo entero", subtitle="COD-1")]

    dialog = OrderFormDialog(branch_id="br-1", warehouse_id="wh-1",
                             supplier_provider=lambda _q: [], product_provider=products)
    dialog._lines._product.set_selected_label("p1", "Pollo entero")
    dialog._lines._qty.set_decimal("10")
    dialog._lines._price.set_decimal("100")
    dialog._lines._conversion.set_decimal("12")
    dialog._lines._add()

    lines = dialog._lines.lines()
    assert lines == [{"product_id": "p1", "quantity": "10.000",
                      "purchase_nature": "INVENTORY", "unit_price": "100.00",
                      "estimated_unit_cost": "100.00", "conversion_factor": "12.000"}]


def test_analytics_kpis_and_charts(app, conn):
    presenter = build_enterprise_presenter(conn, Session())
    presenter.create_order(
        supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "quantity": "10", "unit_price": "100"}])
    kpis = presenter.analytics_kpis()
    assert kpis.open_requisitions >= 0
    charts = presenter.analytics_charts()
    assert len(charts) == 3
    # chart DTOs are color-free and carry a valid canonical type
    for dto in charts:
        assert dto.chart_type in {"donut", "horizontal_bar", "bar"}


def test_analytics_service_empty_is_graceful(app, conn):
    svc = ProcurementAnalyticsService(conn)
    charts = svc.all_charts()
    assert all(c.is_empty() for c in charts)  # no data yet


class ToggleableSession:
    """Mirrors the real pre-login → post-login lifecycle: MainWindow builds
    every module's widget before login (session inactive, no permisos), then
    calls session.set_permisos(...) + widget.refresh_permissions() afterward
    (interfaz/main_window.py::_propagar_usuario)."""

    user_id = "user-1"
    active_branch_id = "br-1"
    active_warehouse_id = "wh-1"
    nombre_completo = "Comprador de prueba"

    def __init__(self) -> None:
        self.is_active = False
        self._grants: set[str] = set()

    def tiene_permiso(self, code) -> bool:
        return code in self._grants

    def set_permisos(self, permisos) -> None:
        self._grants = set(permisos)
        self.is_active = True


# ── 5. Compras se construye antes del login; refresh_permissions() lo repara ─
def test_shell_built_pre_login_shows_routes_after_refresh_permissions(app, conn):
    from frontend.desktop.modules.purchasing.enterprise_routes import (
        create_enterprise_purchasing_view,
    )
    from backend.application.procurement.permissions import PurchasePermissions

    session = ToggleableSession()
    container = type("Container", (), {"db": conn, "session": session})()
    view = create_enterprise_purchasing_view(container)  # pre-login: sin permisos

    labels_before = [view.sidebar.item(row).text() for row in range(view.sidebar.count())]
    assert "Sin acceso" in labels_before
    assert "Solicitudes" not in labels_before

    session.set_permisos({
        PurchasePermissions.VIEW, PurchasePermissions.REQUISITION_VIEW,
        PurchasePermissions.REQUISITION_CREATE,
    })
    view.refresh_permissions()

    labels_after = [view.sidebar.item(row).text() for row in range(view.sidebar.count())]
    assert "Solicitudes" in labels_after
    assert "Sin acceso" not in labels_after


# ── 6. un cambio de permisos posterior se refleja sin reconstruir el widget ─
def test_refresh_permissions_reflects_reduced_grants_live(app, conn):
    from frontend.desktop.modules.purchasing.enterprise_routes import (
        create_enterprise_purchasing_view,
    )
    from backend.application.procurement.permissions import PurchasePermissions

    session = ToggleableSession()
    container = type("Container", (), {"db": conn, "session": session})()
    view = create_enterprise_purchasing_view(container)
    view_identity = id(view)

    session.set_permisos({
        PurchasePermissions.VIEW, PurchasePermissions.REQUISITION_VIEW,
        PurchasePermissions.ORDER_VIEW,
    })
    view.refresh_permissions()
    labels = [view.sidebar.item(row).text() for row in range(view.sidebar.count())]
    assert "Solicitudes" in labels and "Órdenes de compra" in labels

    # un administrador retira el permiso de órdenes en Configuración; MainWindow
    # vuelve a llamar session.set_permisos(...) + refresh_permissions() en vivo
    session.set_permisos({PurchasePermissions.VIEW, PurchasePermissions.REQUISITION_VIEW})
    view.refresh_permissions()
    labels = [view.sidebar.item(row).text() for row in range(view.sidebar.count())]
    assert "Solicitudes" in labels
    assert "Órdenes de compra" not in labels
    assert id(view) == view_identity  # mismo widget, no reconstrucción


# ── FASE 4 (flujo documental): RFQ → cotizaciones → comparación → adjudicación
def test_quotation_flow_end_to_end_through_the_presenter(app, conn):
    """Before this, CaptureSupplierQuoteUseCase/AwardSupplierQuoteUseCase were
    fully implemented and tested in isolation, but the desktop app had no
    screen for them at all — this is the regression test for that gap."""
    conn.execute("INSERT INTO proveedores VALUES ('s2','Proveedor Dos',1)")
    presenter = build_enterprise_presenter(conn, Session())

    ok, _msg, data = presenter.create_requisition(
        branch_id="br-1", purchase_type="INVENTORY", priority="NORMAL",
        business_reason="reabasto", lines=[{"product_id": "p1", "quantity": "10"}])
    assert ok
    rid = data["entity_id"]
    assert presenter.submit_requisition(rid)[0]

    class Approver(Session):
        user_id = "approver-1"

    approver = build_enterprise_presenter(conn, Approver())
    assert approver.approve_requisition(rid, approve=True)[0]

    ok, msg, data = presenter.create_rfq_from_requisition(rid, ["s1", "s2"])
    assert ok, msg
    rfq_id = data["entity_id"]

    model = presenter.rfqs()
    assert model.total == 1
    assert model.rows[0][2] == "2"  # invitados

    detail = presenter.rfq_detail(rfq_id)
    assert {inv.supplier_name for inv in detail.invitations} == {"Proveedor Uno", "Proveedor Dos"}

    ok, msg, _ = presenter.capture_quote(
        rfq_id=rfq_id, supplier_id="s1", lead_time_days=5,
        lines=[{"product_id": "p1", "quantity": "10", "unit_price": "90"}])
    assert ok, msg
    ok, msg, _ = presenter.capture_quote(
        rfq_id=rfq_id, supplier_id="s2", lead_time_days=2,
        lines=[{"product_id": "p1", "quantity": "10", "unit_price": "80"}])
    assert ok, msg

    comparison = presenter.quote_comparison(rfq_id)
    best = next(r for r in comparison if r.is_best)
    assert best.supplier_name == "Proveedor Dos"  # cheapest wins the rank

    ok, msg, _ = presenter.award_quote(award_lines=[{
        "quote_line_id": best.quote_line_id, "supplier_id": best.supplier_id,
        "awarded_quantity": best.quantity, "justification": "mejor precio"}])
    assert ok, msg
    assert presenter.rfq_detail(rfq_id).awarded is True


def test_quotations_page_builds_headless_and_shows_captured_quotes(app, conn):
    from frontend.desktop.modules.purchasing.pages.enterprise_pages import QuotationsPage

    conn.execute("INSERT INTO proveedores VALUES ('s2','Proveedor Dos',1)")
    presenter = build_enterprise_presenter(conn, Session())
    ok, _m, data = presenter.create_requisition(
        branch_id="br-1", purchase_type="INVENTORY", priority="NORMAL",
        business_reason="reabasto", lines=[{"product_id": "p1", "quantity": "10"}])
    rid = data["entity_id"]
    presenter.submit_requisition(rid)

    class Approver(Session):
        user_id = "approver-1"

    build_enterprise_presenter(conn, Approver()).approve_requisition(rid, approve=True)
    _, _, data = presenter.create_rfq_from_requisition(rid, ["s1", "s2"])
    presenter.capture_quote(
        rfq_id=data["entity_id"], supplier_id="s1", lead_time_days=5,
        lines=[{"product_id": "p1", "quantity": "10", "unit_price": "90"}])

    page = QuotationsPage(presenter)
    page.reload()
    assert page._table.rowCount() == 1


def test_award_dialog_builds_award_lines_from_selected_rows(app, conn):
    from frontend.desktop.modules.purchasing.dialogs.enterprise_dialogs import AwardDialog
    from backend.application.procurement.dto.quotation_dtos import ComparisonRowDTO

    rows = [
        ComparisonRowDTO(product_id="p1", quote_id="q1", quote_line_id="ql1",
                         supplier_id="s2", supplier_name="Proveedor Dos", quantity="10",
                         unit_price="80", lead_time_days=2, currency_code="MXN", is_best=True),
        ComparisonRowDTO(product_id="p1", quote_id="q2", quote_line_id="ql2",
                         supplier_id="s1", supplier_name="Proveedor Uno", quantity="10",
                         unit_price="90", lead_time_days=5, currency_code="MXN", is_best=False),
    ]
    dialog = AwardDialog(comparison_rows=rows)
    assert dialog.award_lines() == []  # nothing picked yet — never invents a winner

    dialog._table.selectRow(0)
    dialog._reason.setPlainText("mejor precio")
    lines = dialog.award_lines()
    assert lines == [{"quote_line_id": "ql1", "supplier_id": "s2",
                      "awarded_quantity": "10", "justification": "mejor precio"}]
