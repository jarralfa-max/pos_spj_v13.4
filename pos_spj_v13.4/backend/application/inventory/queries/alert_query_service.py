"""AlertQueryService — the read the Inventario «Alertas» UI consults (§23).

Read-only projection over ``inventory_notification_log``: lists recent alerts
dispatched by the inventory notification engine (low stock, expiry, cold-chain…)
per branch — date, severity, event, channel, status and message — most recent
first, bounded. It never writes; the log is appended by the notification service.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    zn,
)


class AlertQueryService(InventoryRepositoryBase):
    def list_recent(self, *, branch_id: str | None = None,
                    severity: str | None = None,
                    limit: int = 200) -> list[dict]:
        """Recent alerts (most recent first, bounded), optionally scoped to a
        branch and to an exact severity. Rows carry date, severity, event,
        channel, status and message."""
        cols = ("created_at, severity, event_name, channel, status, message")
        lim = max(1, int(limit))
        where, params = [], []
        if branch_id:
            where.append("branch_id=?")
            params.append(branch_id)
        if severity:
            where.append("severity=?")
            params.append(severity)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self._query(
            f"SELECT {cols} FROM inventory_notification_log{clause}"
            " ORDER BY created_at DESC, id DESC LIMIT ?", tuple(params) + (lim,))
        return [{
            "created_at": r["created_at"], "severity": r["severity"],
            "event_name": r["event_name"], "channel": r["channel"],
            "status": r["status"], "message": zn(r["message"]),
        } for r in rows]
