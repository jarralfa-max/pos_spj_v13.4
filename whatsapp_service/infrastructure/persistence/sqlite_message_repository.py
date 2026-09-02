# infrastructure/persistence/sqlite_message_repository.py — WA-4
"""Implementación SQLite de `WhatsAppMessageRepository` contra
`whatsapp_messages`/`whatsapp_message_deliveries` (migración 243)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from domain.whatsapp.entities.message import WhatsAppMessage, WhatsAppMessageDelivery
from domain.whatsapp.enums import MessageDeliveryStatus, MessageDirection, MessageType

_MESSAGE_COLUMNS = (
    "id, conversation_id, direction, message_type, provider_message_id, "
    "payload_reference, correlation_id, operation_id, created_at"
)


def _message_from_row(row) -> WhatsAppMessage:
    return WhatsAppMessage(
        id=row[0],
        conversation_id=row[1],
        direction=MessageDirection(row[2]),
        message_type=MessageType(row[3]),
        provider_message_id=row[4],
        payload_reference=row[5],
        correlation_id=row[6],
        operation_id=row[7],
        created_at=datetime.fromisoformat(row[8]),
    )


_DELIVERY_COLUMNS = (
    "id, message_id, status, sent_at, delivered_at, read_at, failed_at, "
    "error_code, attempt_count, updated_at"
)


def _delivery_from_row(row) -> WhatsAppMessageDelivery:
    return WhatsAppMessageDelivery(
        id=row[0],
        message_id=row[1],
        status=MessageDeliveryStatus(row[2]),
        sent_at=datetime.fromisoformat(row[3]) if row[3] else None,
        delivered_at=datetime.fromisoformat(row[4]) if row[4] else None,
        read_at=datetime.fromisoformat(row[5]) if row[5] else None,
        failed_at=datetime.fromisoformat(row[6]) if row[6] else None,
        error_code=row[7],
        attempt_count=row[8],
        updated_at=datetime.fromisoformat(row[9]),
    )


class SqliteWhatsAppMessageRepository:
    """Implementa `WhatsAppMessageRepository`."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_id(self, message_id: str) -> Optional[WhatsAppMessage]:
        row = self._conn.execute(
            f"SELECT {_MESSAGE_COLUMNS} FROM whatsapp_messages WHERE id=?", (message_id,)
        ).fetchone()
        return _message_from_row(row) if row else None

    def get_by_provider_message_id(self, provider_message_id: str) -> Optional[WhatsAppMessage]:
        row = self._conn.execute(
            f"SELECT {_MESSAGE_COLUMNS} FROM whatsapp_messages WHERE provider_message_id=?",
            (provider_message_id,),
        ).fetchone()
        return _message_from_row(row) if row else None

    def save(self, message: WhatsAppMessage) -> None:
        self._conn.execute(
            "INSERT INTO whatsapp_messages "
            f"({_MESSAGE_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                message.id,
                message.conversation_id,
                message.direction.value,
                message.message_type.value,
                message.provider_message_id,
                message.payload_reference,
                message.correlation_id,
                message.operation_id,
                message.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get_delivery(self, delivery_id: str) -> Optional[WhatsAppMessageDelivery]:
        row = self._conn.execute(
            f"SELECT {_DELIVERY_COLUMNS} FROM whatsapp_message_deliveries WHERE id=?",
            (delivery_id,),
        ).fetchone()
        return _delivery_from_row(row) if row else None

    def get_delivery_for_message(self, message_id: str) -> Optional[WhatsAppMessageDelivery]:
        row = self._conn.execute(
            f"SELECT {_DELIVERY_COLUMNS} FROM whatsapp_message_deliveries WHERE message_id=?",
            (message_id,),
        ).fetchone()
        return _delivery_from_row(row) if row else None

    def save_delivery(self, delivery: WhatsAppMessageDelivery) -> None:
        self._conn.execute(
            "INSERT INTO whatsapp_message_deliveries "
            f"({_DELIVERY_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "status=excluded.status, "
            "sent_at=excluded.sent_at, "
            "delivered_at=excluded.delivered_at, "
            "read_at=excluded.read_at, "
            "failed_at=excluded.failed_at, "
            "error_code=excluded.error_code, "
            "attempt_count=excluded.attempt_count, "
            "updated_at=excluded.updated_at",
            (
                delivery.id,
                delivery.message_id,
                delivery.status.value,
                delivery.sent_at.isoformat() if delivery.sent_at else None,
                delivery.delivered_at.isoformat() if delivery.delivered_at else None,
                delivery.read_at.isoformat() if delivery.read_at else None,
                delivery.failed_at.isoformat() if delivery.failed_at else None,
                delivery.error_code,
                delivery.attempt_count,
                delivery.updated_at.isoformat(),
            ),
        )
        self._conn.commit()
