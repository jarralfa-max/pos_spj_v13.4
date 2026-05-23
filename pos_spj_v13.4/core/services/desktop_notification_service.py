from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from core.services.notification_sound_service import NotificationSoundService


class DesktopNotificationService:
    """Central ERP desktop notification service with dedupe + severity."""

    def __init__(self, db, sound_service: Optional[NotificationSoundService] = None):
        self.db = db
        self.sound_service = sound_service or NotificationSoundService()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_inbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER,
                tipo TEXT NOT NULL,
                titulo TEXT NOT NULL,
                cuerpo TEXT DEFAULT '',
                datos TEXT DEFAULT '{}',
                leido INTEGER DEFAULT 0,
                sucursal_id INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                leido_at TEXT,
                dedupe_key TEXT,
                severity TEXT DEFAULT 'info'
            )
            """
        )
        self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_inbox_dedupe_key ON notification_inbox(dedupe_key) WHERE dedupe_key IS NOT NULL")
        self.db.commit()

    def create_notification(
        self,
        *,
        branch_id: int,
        title: str,
        message: str,
        dedupe_key: str,
        severity: str = "info",
        tipo: str = "pedido_whatsapp_nuevo",
        data: Optional[Dict[str, Any]] = None,
        empleado_id: Optional[int] = None,
    ) -> bool:
        if dedupe_key:
            row = self.db.execute("SELECT 1 FROM notification_inbox WHERE dedupe_key=? LIMIT 1", (dedupe_key,)).fetchone()
            if row:
                return False

        self.db.execute(
            """
            INSERT INTO notification_inbox
            (empleado_id, tipo, titulo, cuerpo, datos, sucursal_id, dedupe_key, severity, leido, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))
            """,
            (
                empleado_id,
                tipo,
                title,
                message,
                json.dumps(data or {}, ensure_ascii=False, default=str),
                int(branch_id),
                dedupe_key,
                severity,
            ),
        )
        self.db.commit()
        self.sound_service.play_for_notification(dedupe_key=dedupe_key, severity=severity)
        return True

    def notify_new_order(self, *, branch_id: int, sale_id: int, folio: str, total: float) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Nuevo pedido WhatsApp",
            message=f"Folio {folio} · Total ${float(total):.2f}",
            dedupe_key=f"new_order:{sale_id}",
            severity="info",
            tipo="pedido_whatsapp_nuevo",
            data={"sale_id": sale_id, "folio": folio, "total": total, "created_at": datetime.now().isoformat()},
        )

    def notify_scheduled_order(self, *, branch_id: int, sale_id: int, folio: str, scheduled_at: str) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Pedido programado",
            message=f"Folio {folio} · Fecha programada: {scheduled_at}",
            dedupe_key=f"scheduled_order:{sale_id}",
            severity="warning",
            tipo="pedido_whatsapp_programado",
            data={"sale_id": sale_id, "folio": folio, "scheduled_at": scheduled_at},
        )

    def get_unread_notifications(self, *, branch_id: int, limit: int = 50):
        rows = self.db.execute(
            """
            SELECT id, tipo, titulo, cuerpo, datos, sucursal_id, dedupe_key, severity, created_at
            FROM notification_inbox
            WHERE COALESCE(sucursal_id,1)=? AND COALESCE(leido,0)=0
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(branch_id), int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_as_read(self, *, notification_id: int) -> None:
        self.db.execute(
            "UPDATE notification_inbox SET leido=1, leido_at=datetime('now') WHERE id=?",
            (int(notification_id),),
        )
        self.db.commit()
