"""OrdersOverviewPresenter (ORD-28) — feeds the "Resumen" landing page's
KPI bar from ORD-27's read-only query services. Never touches SQL itself —
same "presenter adapts, service queries" split every other module's
presenter already follows (e.g. Losses' `LossAnalyticsPresenter`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from frontend.desktop.components.kpi_card import KPIDTO

from backend.application.orders_delivery.queries.analytics_query_service import (
    OrdersDeliveryAnalyticsQueryService,
)
from backend.application.orders_delivery.queries.order_badge_query_service import (
    OrdersDeliveryBadgeQueryService,
)


class OrdersOverviewPresenter:
    def __init__(self, connection, *, branch_id: str, window_days: int = 30) -> None:
        self._analytics = OrdersDeliveryAnalyticsQueryService(connection)
        self._badges = OrdersDeliveryBadgeQueryService(connection)
        self._branch_id = branch_id
        self._window_days = window_days

    def kpi_cards(self) -> list[KPIDTO]:
        now = datetime.now(timezone.utc)
        date_from = (now - timedelta(days=self._window_days)).isoformat(timespec="seconds")
        date_to = now.isoformat(timespec="seconds")
        kpi = self._analytics.kpi_summary(
            branch_id=self._branch_id, date_from=date_from, date_to=date_to)
        badges = self._badges.get_badge_counts(self._branch_id)
        return [
            KPIDTO("orders_created", "Pedidos (30 días)", str(kpi["orders_created"])),
            KPIDTO("orders_completed", "Completados", str(kpi["orders_completed"])),
            KPIDTO("revenue", "Ingreso completado", f"${kpi['total_revenue']:,.2f}"),
            KPIDTO("active_deliveries", "Entregas activas", str(badges["active_deliveries"])),
            KPIDTO("failed_deliveries", "Entregas fallidas", str(badges["failed_deliveries"]),
                   variant="danger" if badges["failed_deliveries"] else "neutral"),
            KPIDTO("settlements_pending", "Liquidaciones pendientes",
                   str(badges["settlements_pending_review"])),
        ]
