"""NotificationInboxFeed — CRM-43.

Conecta la campana de la barra superior (`NotificationDrawer`, que desde SHELL-11
esperaba una fuente) con la bandeja personal de avisos del ERP
(`UserInboxService` sobre `notification_inbox`): recordatorios del CRM, avisos de
automatizaciones, alertas de productos y de entregas.

Sólo presenta: lee los avisos del usuario de la sesión y, al abrir uno, pide
marcarlo como leído. No hay SQL aquí.
"""
from __future__ import annotations

from datetime import datetime

from frontend.desktop.shell.application_shell.notification_drawer import (
    NotificationDrawer,
    NotificationItem,
)


def _parse(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return datetime.now().astimezone()
    return parsed.astimezone() if parsed.tzinfo else parsed


class NotificationInboxFeed:
    def __init__(self, inbox_service, user_id: str) -> None:
        self._inbox = inbox_service
        self._user_id = user_id
        self._drawer: NotificationDrawer | None = None

    def attach(self, drawer: NotificationDrawer) -> None:
        self._drawer = drawer
        drawer.notification_activated.connect(self.mark_read)

    def refresh(self) -> None:
        if self._drawer is None:
            return
        rows = self._inbox.recent(self._user_id)
        self._drawer.replace_all(tuple(
            NotificationItem(notification_id=row.id, title=row.title, message=row.body,
                             created_at=_parse(row.created_at), read=row.read)
            for row in rows))

    def mark_read(self, notification_id: str) -> None:
        self._inbox.mark_read(self._user_id, notification_id)
