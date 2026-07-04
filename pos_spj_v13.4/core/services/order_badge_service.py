from __future__ import annotations

from typing import Dict, Set


class OrderBadgeService:
    """Compute branch-scoped badge counters from persistent sources.

    This service is intentionally defensive: a missing optional table/column must
    never break the Delivery UI. Counters degrade to 0 when the schema is older
    than the current module.
    """

    ACTIVE_STATUSES = ("pendiente", "preparacion", "en_ruta", "pendiente_wa", "en_preparacion")

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

    def get_badge_counts(self, branch_id: str) -> Dict[str, int]:
        return {
            "orders_active": self._safe_count(self._count_active_orders, branch_id),
            "orders_scheduled": self._safe_count(self._count_scheduled_orders, branch_id),
            "adjustments_pending": self._safe_count(self._count_pending_adjustments, branch_id),
            "notifications_unread": self._safe_count(self._count_unread_notifications, branch_id),
        }

    def _safe_count(self, fn, branch_id: str) -> int:
        try:
            total = fn(branch_id)  # conteo (el branch es sólo filtro)
            return int(total or 0)
        except Exception:
            return 0

    def _table_exists(self, table_name: str) -> bool:
        try:
            row = self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=? LIMIT 1",
                (table_name,),
            ).fetchone()
            return row is not None
        except Exception:
            return False

    def _columns(self, table_name: str) -> Set[str]:
        if not self._table_exists(table_name):
            return set()
        try:
            return {r[1] for r in self.db.execute(f"PRAGMA table_info({table_name})").fetchall()}
        except Exception:
            return set()

    def _count_active_orders(self, branch_id: str) -> int:
        if not self._table_exists("delivery_orders"):
            return 0
        cols = self._columns("delivery_orders")
        branch_expr = "COALESCE(sucursal_id,1)" if "sucursal_id" in cols else "1"
        status_col = "estado" if "estado" in cols else "''"
        row = self.db.execute(
            f"""
            SELECT COUNT(*)
            FROM delivery_orders
            WHERE {branch_expr}=?
              AND lower(COALESCE({status_col},'')) IN ('pendiente','preparacion','en_ruta','pendiente_wa','en_preparacion')
            """,
            (branch_id,),
        ).fetchone()
        return int(row[0] or 0)

    def _count_scheduled_orders(self, branch_id: str) -> int:
        total = 0
        if self._table_exists("delivery_orders"):
            cols = self._columns("delivery_orders")
            branch_expr = "COALESCE(sucursal_id,1)" if "sucursal_id" in cols else "1"
            clauses = []
            if "workflow_type" in cols:
                clauses.append("lower(COALESCE(workflow_type,''))='scheduled'")
            if "estado" in cols:
                clauses.append("lower(COALESCE(estado,'')) IN ('programado','scheduled')")
            if "scheduled_at" in cols:
                clauses.append("COALESCE(scheduled_at,'') != ''")
            if clauses:
                row = self.db.execute(
                    f"SELECT COUNT(*) FROM delivery_orders WHERE {branch_expr}=? AND (" + " OR ".join(clauses) + ")",
                    (branch_id,),
                ).fetchone()
                total += int(row[0] or 0)
        if self._table_exists("ventas"):
            cols = self._columns("ventas")
            branch_expr = "COALESCE(sucursal_id,1)" if "sucursal_id" in cols else "1"
            clauses = []
            if "workflow_type" in cols:
                clauses.append("lower(COALESCE(workflow_type,''))='scheduled'")
            if "estado" in cols:
                clauses.append("lower(COALESCE(estado,'')) IN ('programado','scheduled')")
            if "scheduled_at" in cols:
                clauses.append("COALESCE(scheduled_at,'') != ''")
            if "fecha_entrega_programada" in cols:
                clauses.append("COALESCE(fecha_entrega_programada,'') != ''")
            if clauses:
                row = self.db.execute(
                    f"SELECT COUNT(*) FROM ventas WHERE {branch_expr}=? AND (" + " OR ".join(clauses) + ")",
                    (branch_id,),
                ).fetchone()
                total += int(row[0] or 0)
        return total

    def _count_pending_adjustments(self, branch_id: str) -> int:
        if not self._table_exists("delivery_orders"):
            return 0
        cols = self._columns("delivery_orders")
        if "adjustment_pending" in cols:
            branch_expr = "COALESCE(sucursal_id,1)" if "sucursal_id" in cols else "1"
            row = self.db.execute(
                f"SELECT COUNT(*) FROM delivery_orders WHERE {branch_expr}=? AND COALESCE(adjustment_pending,0)=1",
                (branch_id,),
            ).fetchone()
            return int(row[0] or 0)
        if self._table_exists("delivery_items"):
            item_cols = self._columns("delivery_items")
            if "adjustment_status" in item_cols:
                row = self.db.execute(
                    """
                    SELECT COUNT(DISTINCT d.id)
                    FROM delivery_orders d
                    JOIN delivery_items i ON i.delivery_id=d.id
                    WHERE COALESCE(d.sucursal_id,1)=?
                      AND lower(COALESCE(i.adjustment_status,''))='pending_customer'
                    """,
                    (branch_id,),
                ).fetchone()
                return int(row[0] or 0)
        return 0

    def _count_unread_notifications(self, branch_id: str) -> int:
        if not self._table_exists("notification_inbox"):
            return 0
        cols = self._columns("notification_inbox")
        branch_expr = "COALESCE(sucursal_id,1)" if "sucursal_id" in cols else "1"
        read_expr = "COALESCE(leido,0)" if "leido" in cols else "0"
        row = self.db.execute(
            f"SELECT COUNT(*) FROM notification_inbox WHERE {branch_expr}=? AND {read_expr}=0",
            (branch_id,),
        ).fetchone()
        return int(row[0] or 0)
