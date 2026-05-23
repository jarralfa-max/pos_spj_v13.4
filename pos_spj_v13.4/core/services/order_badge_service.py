from __future__ import annotations

from typing import Dict


class OrderBadgeService:
    """Compute branch-scoped badge counters from persistent sources."""

    ACTIVE_STATUSES = ("pendiente", "preparacion", "en_ruta")

    def __init__(self, db):
        self.db = db

    def get_badge_counts(self, branch_id: int) -> Dict[str, int]:
        active_orders = self._count_active_orders(branch_id)
        scheduled_orders = self._count_scheduled_orders(branch_id)
        pending_adjustments = self._count_pending_adjustments(branch_id)
        unread_notifications = self._count_unread_notifications(branch_id)
        return {
            "orders_active": active_orders,
            "orders_scheduled": scheduled_orders,
            "adjustments_pending": pending_adjustments,
            "notifications_unread": unread_notifications,
        }

    def _count_active_orders(self, branch_id: int) -> int:
        row = self.db.execute(
            """
            SELECT COUNT(*)
            FROM delivery_orders
            WHERE COALESCE(sucursal_id,1)=?
              AND lower(COALESCE(estado,'')) IN ('pendiente','preparacion','en_ruta')
            """,
            (branch_id,),
        ).fetchone()
        return int(row[0] or 0)

    def _count_scheduled_orders(self, branch_id: int) -> int:
        # prefer canonical cols in ventas, fall back to 0 if not available
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(ventas)").fetchall()}
        if "workflow_type" not in cols:
            return 0
        row = self.db.execute(
            """
            SELECT COUNT(*)
            FROM ventas
            WHERE COALESCE(sucursal_id,1)=?
              AND lower(COALESCE(workflow_type,''))='scheduled'
              AND lower(COALESCE(estado,'')) IN ('programado','scheduled')
            """,
            (branch_id,),
        ).fetchone()
        return int(row[0] or 0)

    def _count_pending_adjustments(self, branch_id: int) -> int:
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(delivery_orders)").fetchall()}
        if "adjustment_pending" in cols:
            row = self.db.execute(
                "SELECT COUNT(*) FROM delivery_orders WHERE COALESCE(sucursal_id,1)=? AND COALESCE(adjustment_pending,0)=1",
                (branch_id,),
            ).fetchone()
            return int(row[0] or 0)
        return 0

    def _count_unread_notifications(self, branch_id: int) -> int:
        row = self.db.execute(
            "SELECT COUNT(*) FROM notification_inbox WHERE COALESCE(sucursal_id,1)=? AND COALESCE(leido,0)=0",
            (branch_id,),
        ).fetchone()
        return int(row[0] or 0)
