"""OrdersDeliveryBadgeQueryService — branch-scoped sidebar badge counters
(master prompt §68: "Mostrar badges desde QueryServices", never computed
inline by the UI). Queries the NEW canonical `customer_orders` table built in
ORD-3, not the legacy `delivery_orders` (`core/services/order_badge_service.py`
keeps serving the live `modulos/delivery.py` sidebar off the legacy schema —
this is a parallel, not-yet-wired badge source for the new skeleton built in
ORD-4).

Defensive like its legacy counterpart: a missing/older schema degrades to 0,
it never raises into the UI.
"""

from __future__ import annotations


class OrdersDeliveryBadgeQueryService:
    def __init__(self, db) -> None:
        self.db = db

    def get_badge_counts(self, branch_id: str) -> dict[str, int]:
        return {
            "scheduled_pending_activation": self._safe_count(
                "SELECT COUNT(*) FROM customer_orders "
                "WHERE branch_id=? AND status='CONFIRMED' AND order_type='SCHEDULED'",
                branch_id),
            "pending_confirmation": self._safe_count(
                "SELECT COUNT(*) FROM customer_orders "
                "WHERE branch_id=? AND status='PENDING_CONFIRMATION'",
                branch_id),
            "preparation_queue": self._safe_count(
                "SELECT COUNT(*) FROM customer_orders "
                "WHERE branch_id=? AND fulfillment_status IN ('PENDING','PREPARING')"
                " AND status='IN_FULFILLMENT'",
                branch_id),
            "weight_adjustments_pending": self._safe_count(
                "SELECT COUNT(*) FROM customer_orders "
                "WHERE branch_id=? AND customer_approval_status='PENDING'",
                branch_id),
            "active_deliveries": self._safe_count(
                "SELECT COUNT(*) FROM customer_orders "
                "WHERE branch_id=? AND fulfillment_status='DISPATCHED'",
                branch_id),
            "failed_deliveries": self._safe_count(
                "SELECT COUNT(*) FROM customer_orders "
                "WHERE branch_id=? AND fulfillment_status='FAILED'",
                branch_id),
            # ORD-21 built driver_settlements and ORD-26 built the
            # notification_inbox-backed internal alert — both placeholders
            # below were 0 only because neither existed yet when ORD-4 wrote
            # this service.
            "settlements_pending_review": self._safe_count(
                "SELECT COUNT(*) FROM driver_settlements "
                "WHERE branch_id=? AND status='PENDING_REVIEW'",
                branch_id),
            "critical_alerts": self._safe_count(
                "SELECT COUNT(*) FROM notification_inbox "
                "WHERE sucursal_id=? AND tipo='entrega_fallida' AND leido=0",
                branch_id),
        }

    def _safe_count(self, sql: str, branch_id: str) -> int:
        try:
            row = self.db.execute(sql, (branch_id,)).fetchone()
            return int(row[0] or 0) if row else 0
        except Exception:
            return 0
