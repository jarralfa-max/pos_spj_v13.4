"""El expediente del cliente con la tabla de reparto REAL (2026-10-03).

La base real ordena los pedidos por `fecha_solicitud`; el resumen de reparto
pedía `fecha` y el Expediente y la edición del cliente reventaban para
CUALQUIER cliente ("no such column: fecha")."""

from __future__ import annotations

import sqlite3

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.queries.customer_delivery_summary_query import (
    CustomerDeliverySummaryQuery,
)


def test_summary_works_with_the_real_delivery_columns():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE delivery_orders (id TEXT, cliente_id TEXT, estado TEXT,"
              " fecha_solicitud TEXT)")
    c.execute("CREATE TABLE delivery_order_history (id TEXT, order_id TEXT, reason TEXT,"
              " fecha TEXT)")
    c.executemany("INSERT INTO delivery_orders VALUES (?,?,?,?)", [
        ("o1", "c1", "entregado", "2026-10-01"), ("o2", "c1", "pendiente", "2026-10-02")])
    c.execute("INSERT INTO delivery_order_history VALUES ('h1','o1','cliente ausente','2026-10-01')")
    resumen = CustomerDeliverySummaryQuery(
        c, CustomerAuthorizationPolicy.permissive_for_tests()).get_summary("c1", actor_user_id="u")
    assert resumen.total_deliveries == 2 and resumen.open_deliveries == 1
    assert resumen.last_delivery_status == "pendiente"
    assert resumen.recent_incidents[0].reason == "cliente ausente"
