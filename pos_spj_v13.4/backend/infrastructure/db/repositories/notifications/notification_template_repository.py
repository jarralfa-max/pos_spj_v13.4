"""SqliteNotificationTemplateRepository — persists `NotificationTemplate`
(SET-20). Implements
`backend.domain.notifications.repository_ports.NotificationTemplateRepositoryPort`.
"""

from __future__ import annotations

import json

from backend.domain.notifications.entities.notification_template import NotificationTemplate
from backend.domain.notifications.enums import NotificationChannel
from backend.infrastructure.db.repositories.notifications.base import NotificationsRepositoryBase

_COLS = "id, code, channel, language, parameter_names_json, active, created_at, updated_at"


class SqliteNotificationTemplateRepository(NotificationsRepositoryBase):
    def save(self, template: NotificationTemplate) -> None:
        self._execute(
            f"INSERT INTO notification_templates ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " parameter_names_json=excluded.parameter_names_json, active=excluded.active,"
            " updated_at=excluded.updated_at",
            self._params(template),
        )

    def get(self, template_id: str) -> NotificationTemplate | None:
        row = self._query_one(f"SELECT {_COLS} FROM notification_templates WHERE id=?", (template_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> NotificationTemplate | None:
        row = self._query_one(f"SELECT {_COLS} FROM notification_templates WHERE code=?", (code.strip(),))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[NotificationTemplate]:
        rows = self._query(f"SELECT {_COLS} FROM notification_templates WHERE active=1 ORDER BY code")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(template: NotificationTemplate) -> tuple:
        return (
            template.id, template.code, template.channel.value, template.language,
            json.dumps(list(template.parameter_names)), int(template.active), template.created_at,
            template.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> NotificationTemplate:
        return NotificationTemplate(
            id=row["id"], code=row["code"], channel=NotificationChannel(row["channel"]),
            language=row["language"], parameter_names=tuple(json.loads(row["parameter_names_json"] or "[]")),
            active=bool(row["active"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )
