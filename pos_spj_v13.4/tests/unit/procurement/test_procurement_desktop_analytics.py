import sqlite3

from backend.application.procurement.queries.procurement_analytics_service import (
    ProcurementAnalyticsService,
)
from frontend.desktop.modules.purchasing.enterprise_presenter import (
    EnterprisePurchasingPresenter,
)


def test_alerts_are_calculated_in_query_service_not_ui():
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        CREATE TABLE purchase_orders (status TEXT);
        CREATE TABLE supplier_invoices (status TEXT);
        INSERT INTO purchase_orders VALUES ('PENDING_APPROVAL');
        INSERT INTO purchase_orders VALUES ('SENT');
        INSERT INTO supplier_invoices VALUES ('WITH_DIFFERENCES');
    """)
    alerts = ProcurementAnalyticsService(connection).alerts()
    assert [(alert.code, alert.count) for alert in alerts] == [
        ("PENDING_APPROVAL", 1), ("INVOICE_DIFFERENCE", 1), ("OVERDUE_ORDER", 1),
    ]


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
