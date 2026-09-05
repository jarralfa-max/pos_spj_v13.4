# infrastructure/persistence/sqlite_idempotency_repository.py — WA-10
"""Implementación SQLite de `WhatsAppIdempotencyRepository` contra
`whatsapp_business_operation_idempotency` (migración 243, sin repositorio
propio hasta WA-10)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from domain.whatsapp.entities.business_operation import BusinessOperationIdempotencyRecord
from domain.whatsapp.enums import IdempotencyStatus

_COLUMNS = (
    "id, operation_id, operation_type, aggregate_type, aggregate_id, "
    "fingerprint, status, result_reference, created_at, completed_at"
)


def _from_row(row) -> BusinessOperationIdempotencyRecord:
    return BusinessOperationIdempotencyRecord(
        id=row[0],
        operation_id=row[1],
        operation_type=row[2],
        aggregate_type=row[3],
        aggregate_id=row[4],
        fingerprint=row[5],
        status=IdempotencyStatus(row[6]),
        result_reference=row[7],
        created_at=datetime.fromisoformat(row[8]),
        completed_at=datetime.fromisoformat(row[9]) if row[9] else None,
    )


class SqliteWhatsAppIdempotencyRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_fingerprint(self, fingerprint: str) -> Optional[BusinessOperationIdempotencyRecord]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_business_operation_idempotency WHERE fingerprint=?",
            (fingerprint,),
        ).fetchone()
        return _from_row(row) if row else None

    def save(self, record: BusinessOperationIdempotencyRecord) -> None:
        self._conn.execute(
            "INSERT INTO whatsapp_business_operation_idempotency "
            f"({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "status=excluded.status, "
            "result_reference=excluded.result_reference, "
            "completed_at=excluded.completed_at",
            (
                record.id,
                record.operation_id,
                record.operation_type,
                record.aggregate_type,
                record.aggregate_id,
                record.fingerprint,
                record.status.value,
                record.result_reference,
                record.created_at.isoformat(),
                record.completed_at.isoformat() if record.completed_at else None,
            ),
        )
        self._conn.commit()
