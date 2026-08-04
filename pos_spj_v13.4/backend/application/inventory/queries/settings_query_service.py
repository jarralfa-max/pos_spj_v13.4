"""SettingsQueryService — the read the Inventario «Configuración» UI consults (§23).

Read-only projection over ``inventory_notification_rule``: lists the module's
alerting policy — which event, on which scope, notifies whom, through which
channel, from which minimum severity, with what throttle, and whether it is
active. It never writes; rules are managed by the notification service.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
)


class SettingsQueryService(InventoryRepositoryBase):
    def list_notification_rules(self, *, limit: int = 200) -> list[dict]:
        """Notification rules ordered by event then channel. Rows carry event,
        scope, channel, minimum severity, throttle and active flag."""
        cols = ("event_name, scope_type, scope_id, channel, min_severity,"
                " throttle_seconds, active")
        lim = max(1, int(limit))
        rows = self._query(
            f"SELECT {cols} FROM inventory_notification_rule"
            " ORDER BY event_name, channel LIMIT ?", (lim,))
        return [{
            "event_name": r["event_name"], "scope_type": r["scope_type"],
            "scope_id": r["scope_id"], "channel": r["channel"],
            "min_severity": r["min_severity"],
            "throttle_seconds": int(r["throttle_seconds"] or 0),
            "active": bool(r["active"]),
        } for r in rows]
