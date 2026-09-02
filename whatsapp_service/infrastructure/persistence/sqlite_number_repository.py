# infrastructure/persistence/sqlite_number_repository.py — WA-4
"""Implementación SQLite de `WhatsAppNumberRepository` contra
`whatsapp_channel_numbers` (migración 243)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from domain.whatsapp.entities.channel_number import WhatsAppChannelNumber
from domain.whatsapp.enums import ChannelNumberStatus, ChannelRole
from domain.whatsapp.value_objects.phone_number import WhatsAppPhoneNumber

_COLUMNS = (
    "id, account_id, phone_number_external_id, display_phone_number, "
    "normalized_phone_number, branch_id, channel_role, status, timezone, locale, "
    "created_at, updated_at"
)


def _from_row(row) -> WhatsAppChannelNumber:
    return WhatsAppChannelNumber(
        id=row[0],
        account_id=row[1],
        phone_number_external_id=row[2],
        display_phone_number=row[3],
        normalized_phone_number=WhatsAppPhoneNumber(value=row[4]),
        branch_id=row[5],
        channel_role=ChannelRole(row[6]),
        status=ChannelNumberStatus(row[7]),
        timezone=row[8],
        locale=row[9],
        created_at=datetime.fromisoformat(row[10]),
        updated_at=datetime.fromisoformat(row[11]),
    )


class SqliteWhatsAppNumberRepository:
    """Implementa `WhatsAppNumberRepository`."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_id(self, number_id: str) -> Optional[WhatsAppChannelNumber]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_channel_numbers WHERE id=?", (number_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def get_by_external_id(self, phone_number_external_id: str) -> Optional[WhatsAppChannelNumber]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_channel_numbers WHERE phone_number_external_id=?",
            (phone_number_external_id,),
        ).fetchone()
        return _from_row(row) if row else None

    def get_by_branch(self, branch_id: str) -> List[WhatsAppChannelNumber]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_channel_numbers WHERE branch_id=? ORDER BY created_at",
            (branch_id,),
        ).fetchall()
        return [_from_row(row) for row in rows]

    def get_global_numbers(self) -> List[WhatsAppChannelNumber]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_channel_numbers "
            "WHERE channel_role='GLOBAL_CUSTOMER_SERVICE' ORDER BY created_at"
        ).fetchall()
        return [_from_row(row) for row in rows]

    def save(self, number: WhatsAppChannelNumber) -> None:
        self._conn.execute(
            "INSERT INTO whatsapp_channel_numbers "
            f"({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "account_id=excluded.account_id, "
            "phone_number_external_id=excluded.phone_number_external_id, "
            "display_phone_number=excluded.display_phone_number, "
            "normalized_phone_number=excluded.normalized_phone_number, "
            "branch_id=excluded.branch_id, "
            "channel_role=excluded.channel_role, "
            "status=excluded.status, "
            "timezone=excluded.timezone, "
            "locale=excluded.locale, "
            "updated_at=excluded.updated_at",
            (
                number.id,
                number.account_id,
                number.phone_number_external_id,
                number.display_phone_number,
                number.normalized_phone_number.value,
                number.branch_id,
                number.channel_role.value,
                number.status.value,
                number.timezone,
                number.locale,
                number.created_at.isoformat(),
                number.updated_at.isoformat(),
            ),
        )
        self._conn.commit()
