"""ProductNotificationLogQuery (PROD-22, §35) — historial de alertas de Productos.

Lee `product_notification_log` (cada envío, omisión por repetición o fallo). Los
teléfonos se enmascaran (§36: no exponer datos sensibles innecesarios); a los
usuarios se les muestra el nombre. Read-only.
"""

from __future__ import annotations


def _mask_phone(ref: str) -> str:
    digits = "".join(ch for ch in ref if ch.isdigit())
    return f"•••• {digits[-4:]}" if len(digits) >= 4 else "••••"


class ProductNotificationLogQuery:
    def __init__(self, connection) -> None:
        self._conn = connection

    def recent(self, *, limit: int = 300) -> list[dict]:
        has_users = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='usuarios'").fetchone()
        user_col = "COALESCE(u.nombre, u.usuario)" if has_users else "NULL"
        user_join = "LEFT JOIN usuarios u ON u.id = l.recipient_ref " if has_users else ""
        rows = self._conn.execute(
            f"SELECT l.id, l.created_at, l.alert_type, l.severity, l.channel, "
            f"l.recipient_ref, {user_col}, l.message, l.status, p.code, p.name "
            f"FROM product_notification_log l {user_join}"
            f"LEFT JOIN products p ON p.id = l.entity_id "
            f"ORDER BY l.created_at DESC, l.rowid DESC LIMIT ?", (int(limit),)).fetchall()
        out = []
        for r in rows:
            channel = r[4]
            recipient = (_mask_phone(r[5] or "") if channel == "WHATSAPP"
                         else (r[6] or r[5] or ""))
            out.append({"id": r[0], "created_at": r[1], "alert_type": r[2], "severity": r[3],
                        "channel": channel, "recipient": recipient, "message": r[7],
                        "status": r[8],
                        "product": f"{r[9]} · {r[10]}" if r[10] else ""})
        return out
