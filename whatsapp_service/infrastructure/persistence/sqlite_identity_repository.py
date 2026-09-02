# infrastructure/persistence/sqlite_identity_repository.py — WA-4
"""Implementación SQLite de `WhatsAppIdentityRepository` contra
`whatsapp_identities` (migración 243)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from domain.whatsapp.entities.identity import WhatsAppIdentity
from domain.whatsapp.enums import IdentityStatus
from domain.whatsapp.value_objects.phone_number import WhatsAppPhoneNumber

_COLUMNS = (
    "id, wa_id, normalized_phone, customer_id, identity_status, "
    "first_seen_at, last_seen_at, blocked_at, created_at, updated_at"
)


def _from_row(row) -> WhatsAppIdentity:
    return WhatsAppIdentity(
        id=row[0],
        wa_id=row[1],
        normalized_phone=WhatsAppPhoneNumber(value=row[2]),
        customer_id=row[3],
        identity_status=IdentityStatus(row[4]),
        first_seen_at=datetime.fromisoformat(row[5]),
        last_seen_at=datetime.fromisoformat(row[6]),
        blocked_at=datetime.fromisoformat(row[7]) if row[7] else None,
        created_at=datetime.fromisoformat(row[8]),
        updated_at=datetime.fromisoformat(row[9]),
    )


class SqliteWhatsAppIdentityRepository:
    """Implementa `WhatsAppIdentityRepository`."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_id(self, identity_id: str) -> Optional[WhatsAppIdentity]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_identities WHERE id=?", (identity_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def get_by_wa_id(self, wa_id: str) -> Optional[WhatsAppIdentity]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_identities WHERE wa_id=?", (wa_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def get_by_normalized_phone(self, e164_phone: str) -> Optional[WhatsAppIdentity]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_identities "
            "WHERE normalized_phone=? ORDER BY last_seen_at DESC LIMIT 1",
            (e164_phone,),
        ).fetchone()
        return _from_row(row) if row else None

    def save(self, identity: WhatsAppIdentity) -> None:
        self._conn.execute(
            "INSERT INTO whatsapp_identities "
            f"({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "wa_id=excluded.wa_id, "
            "normalized_phone=excluded.normalized_phone, "
            "customer_id=excluded.customer_id, "
            "identity_status=excluded.identity_status, "
            "last_seen_at=excluded.last_seen_at, "
            "blocked_at=excluded.blocked_at, "
            "updated_at=excluded.updated_at",
            (
                identity.id,
                identity.wa_id,
                identity.normalized_phone.value,
                identity.customer_id,
                identity.identity_status.value,
                identity.first_seen_at.isoformat(),
                identity.last_seen_at.isoformat(),
                identity.blocked_at.isoformat() if identity.blocked_at else None,
                identity.created_at.isoformat(),
                identity.updated_at.isoformat(),
            ),
        )
        self._conn.commit()
