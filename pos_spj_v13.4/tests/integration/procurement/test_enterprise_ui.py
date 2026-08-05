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


def test_order_create_and_list(app, conn):
    presenter = build_enterprise_presenter(conn, Session())
    ok, _m, data = presenter.create_order(
        supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "quantity": "10", "unit_price": "100"}])
    assert ok and data["total"] == "1000.00"
    model = presenter.orders()
    assert model.total == 1


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
