import sqlite3

from backend.application.procurement.queries.procurement_analytics_service import (
    ProcurementAnalyticsService,
)
from frontend.desktop.modules.purchasing.enterprise_presenter import (
    EnterprisePurchasingPresenter,
)


def test_alerts_are_calculated_in_query_service_not_ui():
    connection = sqlite3.connect(":memory:")
    # Auditoría Compras C27: una tabla ausente es un error, no un cero; el
    # fixture trae las columnas que el alcance (C24) consulta.
    connection.executescript("""
        CREATE TABLE purchase_orders (id TEXT, status TEXT, branch_id TEXT, created_at TEXT);
        CREATE TABLE direct_purchases (id TEXT, branch_id TEXT, created_at TEXT);
        CREATE TABLE supplier_invoices (status TEXT, purchase_order_id TEXT,
                                        direct_purchase_id TEXT, created_at TEXT);
        INSERT INTO purchase_orders VALUES ('po1', 'PENDING_APPROVAL', 'b1', '2026-10-01');
        INSERT INTO purchase_orders VALUES ('po2', 'SENT', 'b1', '2026-10-01');
        INSERT INTO supplier_invoices VALUES ('WITH_DIFFERENCES', 'po2', NULL, '2026-10-02');
    """)
    alerts = ProcurementAnalyticsService(connection).alerts()
    assert [(alert.code, alert.count) for alert in alerts] == [
        ("PENDING_APPROVAL", 1), ("INVOICE_DIFFERENCE", 1), ("OVERDUE_ORDER", 1),
    ]
    # C24: con otra sucursal en el alcance, nada de esto le corresponde.
    assert ProcurementAnalyticsService(connection).alerts(branch_id="b2") == ()


def test_navigation_badges_are_prepared_by_presenter():
    class Snapshot:
        open_requisitions = 4
        pending_order_approvals = 2
        direct_purchases_today = 3
        invoices_with_differences = 5

    presenter = EnterprisePurchasingPresenter(
        connection_provider=lambda: None, read_services={}, analytics=None,
        use_cases={})

    assert presenter.navigation_badges(Snapshot()) == {
        "requisitions": 4, "orders": 2, "direct_purchase": 3,
        "invoices": 5,
    }
