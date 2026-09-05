# infrastructure/persistence/sqlite_inbox_repository.py — WA-6
"""Implementación SQLite de `WhatsAppInboxRepository` contra
`whatsapp_inbox` (migración 243)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from domain.whatsapp.entities.inbox_job import InboundMessageJob
from domain.whatsapp.enums import InboxStatus

_COLUMNS = "id, message_id, status, attempts, last_error, locked_at, created_at, processed_at"


def _from_row(row) -> InboundMessageJob:
    return InboundMessageJob(
        id=row[0],
        message_id=row[1],
        status=InboxStatus(row[2]),
        attempts=row[3],
        last_error=row[4],
        locked_at=datetime.fromisoformat(row[5]) if row[5] else None,
        created_at=datetime.fromisoformat(row[6]),
        processed_at=datetime.fromisoformat(row[7]) if row[7] else None,
    )


class SqliteWhatsAppInboxRepository:
    """Implementa `WhatsAppInboxRepository`.

    `claim_pending` no es atómico frente a múltiples procesos worker
    concurrentes (lee, transiciona en Python, escribe) — aceptable hoy
    porque el microservicio corre en un solo proceso (mismo límite ya
    documentado para el cache de nonces de `service_auth.py`, WA-1); un
    despliegue multi-worker necesitaría `UPDATE ... RETURNING` o un lock
    explícito.
    """

    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_id(self, job_id: str) -> Optional[InboundMessageJob]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_inbox WHERE id=?", (job_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def get_by_message_id(self, message_id: str) -> Optional[InboundMessageJob]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_inbox WHERE message_id=?", (message_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def claim_pending(self, limit: int = 10) -> List[InboundMessageJob]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_inbox WHERE status IN ('PENDING','RETRY') "
            "ORDER BY created_at LIMIT ?",
            (limit,),
        ).fetchall()
        claimed: List[InboundMessageJob] = []
        for row in rows:
            job = _from_row(row)
            job.claim()
            self.save(job)
            claimed.append(job)
        return claimed

    def save(self, job: InboundMessageJob) -> None:
        self._conn.execute(
            "INSERT INTO whatsapp_inbox "
            f"({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "status=excluded.status, "
            "attempts=excluded.attempts, "
            "last_error=excluded.last_error, "
            "locked_at=excluded.locked_at, "
            "processed_at=excluded.processed_at",
            (
                job.id,
                job.message_id,
                job.status.value,
                job.attempts,
                job.last_error,
                job.locked_at.isoformat() if job.locked_at else None,
                job.created_at.isoformat(),
                job.processed_at.isoformat() if job.processed_at else None,
            ),
        )
        self._conn.commit()
