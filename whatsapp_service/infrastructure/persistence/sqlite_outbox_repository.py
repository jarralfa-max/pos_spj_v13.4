# infrastructure/persistence/sqlite_outbox_repository.py — WA-17
"""Implementación SQLite de `WhatsAppOutboxRepository` contra
`whatsapp_outbox` (migración 243). Mismo patrón de "claim no atómico
entre procesos" ya documentado y aceptado en `sqlite_inbox_repository.py`
(WA-6) — un solo proceso microservicio hoy."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from domain.whatsapp.entities.outbox_message import OutboxMessage
from domain.whatsapp.enums import OutboxMessageStatus

_COLUMNS = (
    "id, message_id, conversation_id, channel_number_id, destination_phone, payload_json, "
    "template_name, operation_id, status, attempts, last_error, next_retry_at, created_at, processed_at"
)


def _from_row(row) -> OutboxMessage:
    return OutboxMessage(
        id=row[0],
        message_id=row[1],
        conversation_id=row[2],
        channel_number_id=row[3],
        destination_phone=row[4],
        payload_json=row[5],
        template_name=row[6],
        operation_id=row[7],
        status=OutboxMessageStatus(row[8]),
        attempts=row[9],
        last_error=row[10],
        next_retry_at=datetime.fromisoformat(row[11]) if row[11] else None,
        created_at=datetime.fromisoformat(row[12]),
        processed_at=datetime.fromisoformat(row[13]) if row[13] else None,
    )


class SqliteWhatsAppOutboxRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_id(self, message_id: str) -> Optional[OutboxMessage]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_outbox WHERE id=?", (message_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> Optional[OutboxMessage]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_outbox WHERE operation_id=?", (operation_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def claim_due(self, limit: int = 10) -> List[OutboxMessage]:
        now = datetime.now(timezone.utc).isoformat()
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_outbox WHERE status='PENDING' "
            "AND (next_retry_at IS NULL OR next_retry_at <= ?) "
            "ORDER BY created_at LIMIT ?",
            (now, limit),
        ).fetchall()
        claimed: List[OutboxMessage] = []
        for row in rows:
            message = _from_row(row)
            message.claim()
            self.save(message)
            claimed.append(message)
        return claimed

    def save(self, message: OutboxMessage) -> None:
        self._conn.execute(
            "INSERT INTO whatsapp_outbox "
            f"({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "status=excluded.status, "
            "attempts=excluded.attempts, "
            "last_error=excluded.last_error, "
            "next_retry_at=excluded.next_retry_at, "
            "processed_at=excluded.processed_at",
            (
                message.id,
                message.message_id,
                message.conversation_id,
                message.channel_number_id,
                message.destination_phone,
                message.payload_json,
                message.template_name,
                message.operation_id,
                message.status.value,
                message.attempts,
                message.last_error,
                message.next_retry_at.isoformat() if message.next_retry_at else None,
                message.created_at.isoformat(),
                message.processed_at.isoformat() if message.processed_at else None,
            ),
        )
        self._conn.commit()
