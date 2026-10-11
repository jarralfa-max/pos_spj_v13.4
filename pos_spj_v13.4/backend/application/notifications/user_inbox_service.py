"""UserInboxService (CRM-43) — lectura y acuse de la bandeja personal.

Lo consume la campana de la barra superior. Cada persona ve y marca sólo sus
propios avisos: el destinatario es el usuario de la sesión, nunca un parámetro
libre de la pantalla.
"""

from __future__ import annotations

from backend.infrastructure.notifications.in_app_inbox_repository import (
    InAppInboxRepository,
    InboxRow,
)

#: Cuántos avisos muestra la campana (los más recientes).
INBOX_PAGE_SIZE = 50


class UserInboxService:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._inbox = InAppInboxRepository(connection)

    def recent(self, user_id: str) -> list[InboxRow]:
        if not user_id:
            return []
        return self._inbox.list_for_user(user_id, limit=INBOX_PAGE_SIZE)

    def unread_count(self, user_id: str) -> int:
        return self._inbox.unread_count(user_id) if user_id else 0

    def mark_read(self, user_id: str, notification_id: str) -> bool:
        if not user_id or not notification_id:
            return False
        changed = self._inbox.mark_read(notification_id, user_id)
        self._conn.commit()
        return changed
