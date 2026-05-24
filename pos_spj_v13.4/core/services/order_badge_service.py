from __future__ import annotations

from typing import Dict


class OrderBadgeService:
    """Compute branch-scoped badge counters from persistent sources."""

    ACTIVE_STATUSES = ("pendiente", "preparacion", "en_ruta")

    def __init__(self, db):
        self.db = db

    def _table_exists(self, table_name: str) -> bool:
        try:
            row = self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            return bool(row)
        except Exception:
            return False

    def _columns(self, table_name: str) -> set[str]:
        try:
            return {str(r[1]) for r in self.db.execute(f"PRAGMA table_info({table_name})").fetchall()}
        except Exception:
            return set()

    def get_badge_counts(self, branch_id: int) -> Dict[str, int]:
        return {
            "orders_active": self._count_active_orders(branch_id),
            "orders_scheduled": self._count_scheduled_orders(branch_id),
            "adjustments_pending": self._count_pending_adjustments(branch_id),
            "notifications_unread": self._count_unread_notifications(branch_id),
        }

    def _count_active_orders(self, branch_id: int) -> int:
        if not self._table_exists("delivery_orders"):
            return 0
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
        if not self._table_exists("ventas"):
            return 0
        cols = self._columns("ventas")
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
        if not self._table_exists("delivery_orders"):
            return 0
        if "adjustment_pending" not in self._columns("delivery_orders"):
            return 0
        row = self.db.execute(
            "SELECT COUNT(*) FROM delivery_orders WHERE COALESCE(sucursal_id,1)=? AND COALESCE(adjustment_pending,0)=1",
            (branch_id,),
        ).fetchone()
        return int(row[0] or 0)

    def _count_unread_notifications(self, branch_id: int) -> int:
        if not self._table_exists("notification_inbox"):
            return 0
        cols = self._columns("notification_inbox")
        if "leido" not in cols:
            return 0
        row = self.db.execute(
            "SELECT COUNT(*) FROM notification_inbox WHERE COALESCE(sucursal_id,1)=? AND COALESCE(leido,0)=0",
            (branch_id,),
        ).fetchone()
        return int(row[0] or 0)
