"""ORD-27 — OrdersDeliveryAnalyticsQueryService: KPI/SLA/driver-performance
read-models over the already-built orders_delivery schema. Pure SQLite,
Decimal-only aggregation done in Python (never SQL SUM/AVG on TEXT-decimal
columns)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.queries.analytics_query_service import (
    OrdersDeliveryAnalyticsQueryService,
)
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_orders_delivery_schema(connection)
    yield connection
    connection.close()


def _insert_order(conn, **overrides):
    row = dict(
        id="o1", branch_id="b1", channel="POS", order_type="STANDARD",
        fulfillment_type="COUNTER", status="DRAFT", fulfillment_status="PENDING",
        customer_approval_status="NOT_REQUIRED",
        grand_total="0", created_at="2026-06-01T10:00:00+00:00", updated_at="t",
    )
    row.update(overrides)
    row.setdefault("operation_id", f"op-{row['id']}")
    cols = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO customer_orders ({cols}) VALUES ({placeholders})",
                 list(row.values()))


def _insert_job(conn, **overrides):
    row = dict(
        id="j1", order_id="o1", branch_id="b1", status="PENDING_ASSIGNMENT",
        created_at="2026-06-01T10:00:00+00:00", updated_at="t",
    )
    row.update(overrides)
    row.setdefault("operation_id", f"jop-{row['id']}")
    cols = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO delivery_jobs ({cols}) VALUES ({placeholders})",
                 list(row.values()))


def _insert_collection(conn, **overrides):
    row = dict(
        id="c1", delivery_job_id="j1", driver_id="d1", payment_method="CASH",
        expected_amount="0", collected_amount="0",
        created_at="2026-06-01T10:00:00+00:00", updated_at="t",
    )
    row.update(overrides)
    cols = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO driver_cash_collections ({cols}) VALUES ({placeholders})",
                 list(row.values()))


class TestKpiSummary:
    def test_counts_orders_by_status_and_sums_completed_revenue(self, conn):
        _insert_order(conn, id="o1", status="COMPLETED", grand_total="100.50")
        _insert_order(conn, id="o2", status="COMPLETED", grand_total="49.50")
        _insert_order(conn, id="o3", status="CANCELLED", grand_total="30.00")
        _insert_order(conn, id="o4", status="REVERSED", grand_total="20.00")

        kpi = OrdersDeliveryAnalyticsQueryService(conn).kpi_summary(
            branch_id="b1", date_from="2026-01-01", date_to="2026-12-31")

        assert kpi["orders_created"] == 4
        assert kpi["orders_completed"] == 2
        assert kpi["orders_cancelled"] == 1
        assert kpi["orders_reversed"] == 1
        assert kpi["total_revenue"] == Decimal("150.00")

    def test_excludes_other_branches_and_out_of_range_dates(self, conn):
        _insert_order(conn, id="o1", branch_id="other", status="COMPLETED", grand_total="999")
        _insert_order(conn, id="o2", status="COMPLETED", grand_total="10",
                       created_at="2020-01-01T00:00:00+00:00")

        kpi = OrdersDeliveryAnalyticsQueryService(conn).kpi_summary(
            branch_id="b1", date_from="2026-01-01", date_to="2026-12-31")

        assert kpi["orders_created"] == 0
        assert kpi["total_revenue"] == Decimal("0")

    def test_degrades_gracefully_on_missing_table(self):
        bare = sqlite3.connect(":memory:")
        kpi = OrdersDeliveryAnalyticsQueryService(bare).kpi_summary(
            branch_id="b1", date_from="2026-01-01", date_to="2026-12-31")
        assert kpi["orders_created"] == 0
        assert kpi["total_revenue"] == Decimal("0")
        bare.close()


class TestSlaBreakdown:
    def test_on_time_and_late_are_measured_only_against_a_promised_window(self, conn):
        _insert_order(conn, id="o1")
        _insert_job(conn, id="j1", status="DELIVERED",
                    delivered_at="2026-06-01T11:50:00+00:00",
                    scheduled_window_end="2026-06-01T12:00:00+00:00")  # on time
        _insert_job(conn, id="j2", order_id="o1", status="DELIVERED",
                    delivered_at="2026-06-01T12:30:00+00:00",
                    scheduled_window_end="2026-06-01T12:00:00+00:00")  # late
        _insert_job(conn, id="j3", order_id="o1", status="DELIVERED",
                    delivered_at="2026-06-01T13:00:00+00:00",
                    scheduled_window_end=None)  # no promise — excluded

        sla = OrdersDeliveryAnalyticsQueryService(conn).sla_breakdown(
            branch_id="b1", date_from="2026-01-01", date_to="2026-12-31")

        assert sla["measurable_deliveries"] == 2
        assert sla["on_time_deliveries"] == 1
        assert sla["late_deliveries"] == 1
        assert sla["on_time_rate"] == Decimal("1") / Decimal("2")

    def test_none_when_nothing_measurable(self, conn):
        sla = OrdersDeliveryAnalyticsQueryService(conn).sla_breakdown(
            branch_id="b1", date_from="2026-01-01", date_to="2026-12-31")
        assert sla["on_time_rate"] is None


class TestDriverPerformance:
    def test_rolls_up_deliveries_and_cash_accuracy_per_driver(self, conn):
        _insert_order(conn, id="o1")
        _insert_job(conn, id="j1", assigned_driver_id="d1", status="DELIVERED",
                    dispatched_at="2026-06-01T10:00:00+00:00",
                    delivered_at="2026-06-01T10:30:00+00:00")
        _insert_job(conn, id="j2", order_id="o1", assigned_driver_id="d1", status="FAILED")
        _insert_job(conn, id="j3", order_id="o1", assigned_driver_id="d2", status="DELIVERED",
                    dispatched_at="2026-06-01T10:00:00+00:00",
                    delivered_at="2026-06-01T10:10:00+00:00")
        _insert_collection(conn, id="c1", delivery_job_id="j1", driver_id="d1",
                           expected_amount="100.00", collected_amount="95.00")

        rows = OrdersDeliveryAnalyticsQueryService(conn).driver_performance(
            branch_id="b1", date_from="2026-01-01", date_to="2026-12-31")

        by_driver = {row["driver_id"]: row for row in rows}
        assert by_driver["d1"]["deliveries_completed"] == 1
        assert by_driver["d1"]["deliveries_failed"] == 1
        assert by_driver["d1"]["avg_delivery_minutes"] == Decimal("30")
        assert by_driver["d1"]["cash_variance"] == Decimal("-5.00")
        assert by_driver["d2"]["deliveries_completed"] == 1
        assert by_driver["d2"]["cash_variance"] == Decimal("0")
        # sorted by completed deliveries descending, both tied at 1 here —
        # just confirm both are present rather than assert exact order
        assert {row["driver_id"] for row in rows} == {"d1", "d2"}

    def test_empty_when_no_jobs_have_a_driver(self, conn):
        rows = OrdersDeliveryAnalyticsQueryService(conn).driver_performance(
            branch_id="b1", date_from="2026-01-01", date_to="2026-12-31")
        assert rows == []
