import sqlite3

from backend.application.procurement.queries.procurement_analytics_service import (
    ProcurementAnalyticsService,
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
