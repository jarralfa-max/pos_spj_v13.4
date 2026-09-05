# infrastructure/persistence/sqlite_delivery_request_repository.py — WA-13
"""Implementación SQLite de `WhatsAppDeliveryRequestRepository` contra
`whatsapp_delivery_requests` (migración 246)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from domain.whatsapp.entities.delivery_request import DeliveryRequest
from domain.whatsapp.enums import DeliveryRequestStatus

_COLUMNS = (
    "id, conversation_id, order_external_id, address, delivery_date, "
    "customer_phone, status, failure_reason, created_at, updated_at"
)


class SqliteWhatsAppDeliveryRequestRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_id(self, request_id: str) -> Optional[DeliveryRequest]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_delivery_requests WHERE id=?", (request_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def get_by_order_external_id(self, order_external_id: str) -> Optional[DeliveryRequest]:
        # `id` (UUIDv7, ordenado por tiempo hasta sub-milisegundo) desempata
        # cuando dos intentos comparten el mismo `created_at` de segundo/
        # microsegundo — mismo criterio que
        # `customer_consent_repository.py::get_latest` (CRM-9).
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_delivery_requests "
            "WHERE order_external_id=? ORDER BY created_at DESC, id DESC LIMIT 1",
            (order_external_id,),
        ).fetchone()
        return self._from_row(row) if row else None

    def save(self, request: DeliveryRequest) -> None:
        self._conn.execute(
            f"INSERT INTO whatsapp_delivery_requests ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "status=excluded.status, failure_reason=excluded.failure_reason, "
            "updated_at=excluded.updated_at",
            (
                request.id,
                request.conversation_id,
                request.order_external_id,
                request.address,
                request.delivery_date,
                request.customer_phone,
                request.status.value,
                request.failure_reason,
                request.created_at.isoformat(),
                request.updated_at.isoformat(),
            ),
        )
        self._conn.commit()

    def _from_row(self, row) -> DeliveryRequest:
        return DeliveryRequest(
            id=row[0],
            conversation_id=row[1],
            order_external_id=row[2],
            address=row[3],
            delivery_date=row[4] or "",
            customer_phone=row[5] or "",
            status=DeliveryRequestStatus(row[6]),
            failure_reason=row[7],
            created_at=datetime.fromisoformat(row[8]),
            updated_at=datetime.fromisoformat(row[9]),
        )
