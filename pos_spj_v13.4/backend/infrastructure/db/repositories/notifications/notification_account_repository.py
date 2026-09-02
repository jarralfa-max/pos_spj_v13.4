"""SqliteNotificationAccountRepository — persists `NotificationAccount`
(SET-20). Implements
`backend.domain.notifications.repository_ports.NotificationAccountRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.notifications.entities.notification_account import NotificationAccount
from backend.domain.notifications.enums import NotificationChannel
from backend.infrastructure.db.repositories.notifications.base import NotificationsRepositoryBase

_COLS = "id, channel, name, credential_reference, integration_instance_id, active, created_at, updated_at"


class SqliteNotificationAccountRepository(NotificationsRepositoryBase):
    def save(self, account: NotificationAccount) -> None:
        self._execute(
            f"INSERT INTO notification_accounts ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " name=excluded.name, credential_reference=excluded.credential_reference,"
            " active=excluded.active, updated_at=excluded.updated_at",
            self._params(account),
        )

    def get(self, account_id: str) -> NotificationAccount | None:
        row = self._query_one(f"SELECT {_COLS} FROM notification_accounts WHERE id=?", (account_id,))
        return self._hydrate(row) if row else None

    def list_by_channel(self, channel: NotificationChannel) -> list[NotificationAccount]:
        rows = self._query(
            f"SELECT {_COLS} FROM notification_accounts WHERE channel=? ORDER BY name", (channel.value,),
        )
        return [self._hydrate(row) for row in rows]

    def list_active(self) -> list[NotificationAccount]:
        rows = self._query(f"SELECT {_COLS} FROM notification_accounts WHERE active=1 ORDER BY name")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(account: NotificationAccount) -> tuple:
        return (
            account.id, account.channel.value, account.name, account.credential_reference,
            account.integration_instance_id, int(account.active), account.created_at, account.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> NotificationAccount:
        return NotificationAccount(
            id=row["id"], channel=NotificationChannel(row["channel"]), name=row["name"],
            credential_reference=row["credential_reference"],
            integration_instance_id=row["integration_instance_id"], active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
