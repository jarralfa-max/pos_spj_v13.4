"""InAppInboxRepository (CRM-43) — la bandeja personal de avisos del ERP.

Lee y escribe la tabla canónica `notification_inbox` (migración 041 + 089), la
misma que ya usan `InAppProductNotifier` y el notificador interno de Delivery.
Hasta CRM-43 nadie la mostraba: la campana de la barra superior
(`NotificationDrawer`) existía sin fuente. Este repositorio es esa fuente.

`empleado_id` es el `usuarios.id` del destinatario (mismo espacio de identidad
que el resto de los notificadores). `dedupe_key` (único cuando no es NULL) hace
idempotente la entrega: un recordatorio o una regla que se evalúa dos veces no
deja dos avisos.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.shared.ids import new_uuid

_COLS = "id, empleado_id, tipo, titulo, cuerpo, datos, sucursal_id, leido, created_at, severity"


@dataclass(frozen=True, slots=True)
class InboxRow:
    id: str
    recipient_user_id: str
    kind: str
    title: str
    body: str
    data: dict
    branch_id: str | None
    read: bool
    created_at: str
    severity: str


class InAppInboxRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def deliver(self, *, recipient_user_id: str, kind: str, title: str, body: str = "",
                data: dict | None = None, branch_id: str | None = None,
                dedupe_key: str | None = None, severity: str = "info") -> bool:
        """Inserta el aviso. Devuelve False si ya existía uno con la misma
        `dedupe_key` (entrega repetida)."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO notification_inbox"
            " (id, empleado_id, tipo, titulo, cuerpo, datos, sucursal_id, created_at,"
            " dedupe_key, severity) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), recipient_user_id, kind, title, body,
             json.dumps(data or {}, ensure_ascii=False, default=str), branch_id, now,
             dedupe_key, severity))
        return cursor.rowcount > 0

    def is_delivered(self, dedupe_key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM notification_inbox WHERE dedupe_key=? LIMIT 1", (dedupe_key,)).fetchone()
        return row is not None

    def list_for_user(self, recipient_user_id: str, *, limit: int,
                      unread_only: bool = False) -> list[InboxRow]:
        where = "empleado_id=?" + (" AND COALESCE(leido,0)=0" if unread_only else "")
        rows = self._conn.execute(
            f"SELECT {_COLS} FROM notification_inbox WHERE {where}"
            " ORDER BY created_at DESC LIMIT ?", (recipient_user_id, limit)).fetchall()
        return [self._hydrate(r) for r in rows]

    def unread_count(self, recipient_user_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM notification_inbox WHERE empleado_id=? AND COALESCE(leido,0)=0",
            (recipient_user_id,)).fetchone()
        return int(row[0] if row else 0)

    def mark_read(self, notification_id: str, recipient_user_id: str) -> bool:
        """Sólo el destinatario puede marcar su aviso como leído."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cursor = self._conn.execute(
            "UPDATE notification_inbox SET leido=1, leido_at=?"
            " WHERE id=? AND empleado_id=? AND COALESCE(leido,0)=0",
            (now, notification_id, recipient_user_id))
        return cursor.rowcount > 0

    @staticmethod
    def _hydrate(row) -> InboxRow:
        try:
            data = json.loads(row[5] or "{}")
        except (TypeError, ValueError):
            data = {}
        return InboxRow(id=row[0], recipient_user_id=row[1], kind=row[2] or "", title=row[3] or "",
                        body=row[4] or "", data=data if isinstance(data, dict) else {},
                        branch_id=row[6], read=bool(row[7]), created_at=row[8] or "",
                        severity=row[9] or "info")
