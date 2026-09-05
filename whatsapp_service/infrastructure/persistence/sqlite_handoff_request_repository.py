# infrastructure/persistence/sqlite_handoff_request_repository.py — WA-16
"""Implementación SQLite de `WhatsAppHandoffRequestRepository` contra
`whatsapp_handoff_requests` (migración 247)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from domain.whatsapp.entities.handoff_request import HandoffRequest
from domain.whatsapp.enums import HandoffStatus

_COLUMNS = (
    "id, conversation_id, branch_id, reason, status, assigned_to_phone, "
    "created_at, updated_at, resolved_at"
)


class SqliteWhatsAppHandoffRequestRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_id(self, request_id: str) -> Optional[HandoffRequest]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_handoff_requests WHERE id=?", (request_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def get_open_for_conversation(self, conversation_id: str) -> Optional[HandoffRequest]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_handoff_requests "
            "WHERE conversation_id=? AND status IN ('OPEN','ASSIGNED') "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        return self._from_row(row) if row else None

    def save(self, request: HandoffRequest) -> None:
        self._conn.execute(
            f"INSERT INTO whatsapp_handoff_requests ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "status=excluded.status, assigned_to_phone=excluded.assigned_to_phone, "
            "updated_at=excluded.updated_at, resolved_at=excluded.resolved_at",
            (
                request.id,
                request.conversation_id,
                request.branch_id,
                request.reason,
                request.status.value,
                request.assigned_to_phone,
                request.created_at.isoformat(),
                request.updated_at.isoformat(),
                request.resolved_at.isoformat() if request.resolved_at else None,
            ),
        )
        self._conn.commit()

    def _from_row(self, row) -> HandoffRequest:
        return HandoffRequest(
            id=row[0],
            conversation_id=row[1],
            branch_id=row[2],
            reason=row[3],
            status=HandoffStatus(row[4]),
            assigned_to_phone=row[5],
            created_at=datetime.fromisoformat(row[6]),
            updated_at=datetime.fromisoformat(row[7]),
            resolved_at=datetime.fromisoformat(row[8]) if row[8] else None,
        )
