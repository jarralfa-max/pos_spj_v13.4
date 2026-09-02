"""OrdersDeliveryAnalyticsQueryService (master prompt ORD-27 "1. KPI. 3. SLA.
4. Driver performance."). A pure read-model over the already-built
`customer_orders`/`delivery_jobs`/`delivery_attempts`/`driver_cash_collections`
tables — no new domain mutations, matching the master prompt's own framing
of analytics as a reporting layer, not a write path.

Money/duration aggregation is done in PYTHON with `Decimal`, never via SQL
`SUM()`/`AVG()` on the TEXT-decimal columns — SQLite's aggregate functions
coerce TEXT to REAL (float), which REGLA CERO forbids for money and this
service extends to duration math for the same "no silent float drift"
reasoning. Defensive like `OrdersDeliveryBadgeQueryService` (ORD-4): a
missing/older schema degrades to empty/zeroed results, never raises into a
dashboard.

**"2. Charts" is deliberately NOT built here** — this service returns the
structured data a chart would render (already exactly what a charting
library needs: labeled series, not a picture), but drawing an actual PyQt5
chart widget is a frontend task, honestly out of scope for what a backend
query service can deliver, same "backend real, frontend deferred/flagged"
split ORD-25's PWA phase already used.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _minutes_between(start: str | None, end: str | None) -> Decimal | None:
    start_dt, end_dt = _parse(start), _parse(end)
    if start_dt is None or end_dt is None:
        return None
    seconds = (end_dt - start_dt).total_seconds()
    if seconds < 0:
        return None
    return Decimal(str(seconds)) / Decimal(60)


def _avg(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


class OrdersDeliveryAnalyticsQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def kpi_summary(self, *, branch_id: str, date_from: str, date_to: str) -> dict:
        """Order-level counters + revenue for `branch_id` within
        [date_from, date_to) on `customer_orders.created_at`. Revenue only
        counts COMPLETED orders — a cancelled/failed order was never really
        realized revenue."""
        try:
            rows = self._conn.execute(
                "SELECT status, grand_total FROM customer_orders"
                " WHERE branch_id=? AND created_at>=? AND created_at<?",
                (branch_id, date_from, date_to)).fetchall()
        except Exception:
            rows = []
        counts: dict[str, int] = defaultdict(int)
        revenue = Decimal("0")
        for status, grand_total in rows:
            counts[status] += 1
            if status == "COMPLETED":
                revenue += Decimal(str(grand_total or "0"))
        return {
            "orders_created": len(rows),
            "orders_completed": counts.get("COMPLETED", 0),
            "orders_cancelled": counts.get("CANCELLED", 0),
            "orders_reversed": counts.get("REVERSED", 0),
            "total_revenue": revenue,
        }

    def sla_breakdown(self, *, branch_id: str, date_from: str, date_to: str) -> dict:
        """On-time rate among DELIVERED jobs that actually had a promised
        `scheduled_window_end` — a job with no promised window has no SLA to
        measure against, so it is excluded from the denominator rather than
        silently counted as either a pass or a fail."""
        try:
            rows = self._conn.execute(
                "SELECT delivered_at, scheduled_window_end FROM delivery_jobs"
                " WHERE branch_id=? AND status IN ('DELIVERED','CLOSED')"
                " AND delivered_at IS NOT NULL AND created_at>=? AND created_at<?",
                (branch_id, date_from, date_to)).fetchall()
        except Exception:
            rows = []
        measurable = [(d, w) for d, w in rows if w]
        on_time = sum(1 for d, w in measurable if (_parse(d) or datetime.max) <= _parse(w))
        total = len(measurable)
        return {
            "measurable_deliveries": total,
            "on_time_deliveries": on_time,
            "late_deliveries": total - on_time,
            "on_time_rate": (Decimal(on_time) / Decimal(total)) if total else None,
        }

    def driver_performance(self, *, branch_id: str, date_from: str, date_to: str) -> list[dict]:
        """Per-driver rollup: deliveries completed/failed, average minutes
        from dispatch to delivery, and cash-collection accuracy (collected
        vs. expected across `driver_cash_collections` for that driver's jobs
        in range)."""
        try:
            jobs = self._conn.execute(
                "SELECT assigned_driver_id, status, dispatched_at, delivered_at FROM delivery_jobs"
                " WHERE branch_id=? AND assigned_driver_id IS NOT NULL"
                " AND created_at>=? AND created_at<?",
                (branch_id, date_from, date_to)).fetchall()
        except Exception:
            jobs = []
        by_driver: dict[str, dict] = defaultdict(
            lambda: {"completed": 0, "failed": 0, "durations": []})
        for driver_id, status, dispatched_at, delivered_at in jobs:
            bucket = by_driver[driver_id]
            if status in ("DELIVERED", "CLOSED"):
                bucket["completed"] += 1
                minutes = _minutes_between(dispatched_at, delivered_at)
                if minutes is not None:
                    bucket["durations"].append(minutes)
            elif status == "FAILED":
                bucket["failed"] += 1

        try:
            collections = self._conn.execute(
                "SELECT driver_id, expected_amount, collected_amount FROM driver_cash_collections"
                " WHERE driver_id IN (SELECT DISTINCT assigned_driver_id FROM delivery_jobs"
                " WHERE branch_id=? AND assigned_driver_id IS NOT NULL)",
                (branch_id,)).fetchall()
        except Exception:
            collections = []
        cash_totals: dict[str, tuple[Decimal, Decimal]] = defaultdict(
            lambda: (Decimal("0"), Decimal("0")))
        for driver_id, expected, collected in collections:
            expected_total, collected_total = cash_totals[driver_id]
            cash_totals[driver_id] = (
                expected_total + Decimal(str(expected or "0")),
                collected_total + Decimal(str(collected or "0")))

        results = []
        for driver_id, bucket in by_driver.items():
            expected_total, collected_total = cash_totals.get(driver_id, (Decimal("0"), Decimal("0")))
            results.append({
                "driver_id": driver_id,
                "deliveries_completed": bucket["completed"],
                "deliveries_failed": bucket["failed"],
                "avg_delivery_minutes": _avg(bucket["durations"]),
                "cash_expected": expected_total,
                "cash_collected": collected_total,
                "cash_variance": collected_total - expected_total,
            })
        results.sort(key=lambda r: r["deliveries_completed"], reverse=True)
        return results
