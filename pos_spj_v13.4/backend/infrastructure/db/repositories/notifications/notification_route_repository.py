"""SqliteNotificationRouteRepository — persists `NotificationRoute`
(SET-20). Implements
`backend.domain.notifications.repository_ports.NotificationRouteRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.notifications.entities.notification_route import NotificationRoute
from backend.domain.notifications.enums import NotificationChannel
from backend.infrastructure.db.repositories.notifications.base import NotificationsRepositoryBase

_COLS = "id, event_code, channel, template_id, account_id, active, created_at, updated_at"


class SqliteNotificationRouteRepository(NotificationsRepositoryBase):
    def save(self, route: NotificationRoute) -> None:
        self._execute(
            f"INSERT INTO notification_routes ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " active=excluded.active, updated_at=excluded.updated_at",
            self._params(route),
        )

    def get(self, route_id: str) -> NotificationRoute | None:
        row = self._query_one(f"SELECT {_COLS} FROM notification_routes WHERE id=?", (route_id,))
        return self._hydrate(row) if row else None

    def list_by_event_code(self, event_code: str) -> list[NotificationRoute]:
        rows = self._query(
            f"SELECT {_COLS} FROM notification_routes WHERE event_code=?", (event_code.strip(),),
        )
        return [self._hydrate(row) for row in rows]

    def list_active(self) -> list[NotificationRoute]:
        rows = self._query(f"SELECT {_COLS} FROM notification_routes WHERE active=1 ORDER BY event_code")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(route: NotificationRoute) -> tuple:
        return (
            route.id, route.event_code, route.channel.value, route.template_id, route.account_id,
            int(route.active), route.created_at, route.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> NotificationRoute:
        return NotificationRoute(
            id=row["id"], event_code=row["event_code"], channel=NotificationChannel(row["channel"]),
            template_id=row["template_id"], account_id=row["account_id"], active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
