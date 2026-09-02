# infrastructure/persistence/sqlite_conversation_repository.py — WA-4
"""Implementación SQLite de `WhatsAppConversationRepository` contra
`whatsapp_conversations`/`whatsapp_conversation_sessions` (migración 243).

`ConversationContext` (WA-2, dataclass tipada y versionada) se serializa a
`context_json` como un objeto plano de sus propios campos — nunca un pickle
ni un `repr()` de Python (§14 del prompt maestro: prohibido guardar
objetos serializados arbitrariamente)."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Optional

from domain.whatsapp.entities.conversation import ConversationSession, WhatsAppConversation
from domain.whatsapp.entities.conversation_context import ConversationContext
from domain.whatsapp.enums import ConversationState

_CONVERSATION_COLUMNS = (
    "id, identity_id, channel_number_id, branch_id, state, context_json, "
    "context_version, current_session_id, opened_at, closed_at, last_message_at, updated_at"
)


def _context_from_json(raw: str, version: int) -> ConversationContext:
    data = json.loads(raw) if raw else {}
    data.pop("version", None)
    return ConversationContext(version=version, **data)


def _conversation_from_row(row) -> WhatsAppConversation:
    return WhatsAppConversation(
        id=row[0],
        identity_id=row[1],
        channel_number_id=row[2],
        branch_id=row[3],
        state=ConversationState(row[4]),
        context=_context_from_json(row[5], row[6]),
        current_session_id=row[7],
        opened_at=datetime.fromisoformat(row[8]),
        closed_at=datetime.fromisoformat(row[9]) if row[9] else None,
        last_message_at=datetime.fromisoformat(row[10]) if row[10] else None,
        updated_at=datetime.fromisoformat(row[11]),
    )


class SqliteWhatsAppConversationRepository:
    """Implementa `WhatsAppConversationRepository`."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_id(self, conversation_id: str) -> Optional[WhatsAppConversation]:
        row = self._conn.execute(
            f"SELECT {_CONVERSATION_COLUMNS} FROM whatsapp_conversations WHERE id=?",
            (conversation_id,),
        ).fetchone()
        return _conversation_from_row(row) if row else None

    def get_open_for_identity(
        self, identity_id: str, channel_number_id: str
    ) -> Optional[WhatsAppConversation]:
        row = self._conn.execute(
            f"SELECT {_CONVERSATION_COLUMNS} FROM whatsapp_conversations "
            "WHERE identity_id=? AND channel_number_id=? AND closed_at IS NULL "
            "ORDER BY opened_at DESC LIMIT 1",
            (identity_id, channel_number_id),
        ).fetchone()
        return _conversation_from_row(row) if row else None

    def save(self, conversation: WhatsAppConversation) -> None:
        context_dict = asdict(conversation.context)
        context_dict.pop("version", None)
        self._conn.execute(
            "INSERT INTO whatsapp_conversations "
            f"({_CONVERSATION_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "branch_id=excluded.branch_id, "
            "state=excluded.state, "
            "context_json=excluded.context_json, "
            "context_version=excluded.context_version, "
            "current_session_id=excluded.current_session_id, "
            "closed_at=excluded.closed_at, "
            "last_message_at=excluded.last_message_at, "
            "updated_at=excluded.updated_at",
            (
                conversation.id,
                conversation.identity_id,
                conversation.channel_number_id,
                conversation.branch_id,
                conversation.state.value,
                json.dumps(context_dict, ensure_ascii=False),
                conversation.context.version,
                conversation.current_session_id,
                conversation.opened_at.isoformat(),
                conversation.closed_at.isoformat() if conversation.closed_at else None,
                conversation.last_message_at.isoformat() if conversation.last_message_at else None,
                conversation.updated_at.isoformat(),
            ),
        )
        self._conn.commit()

    def save_session(self, session: ConversationSession) -> None:
        self._conn.execute(
            "INSERT INTO whatsapp_conversation_sessions "
            "(id, conversation_id, started_at, ended_at) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET ended_at=excluded.ended_at",
            (
                session.id,
                session.conversation_id,
                session.started_at.isoformat(),
                session.ended_at.isoformat() if session.ended_at else None,
            ),
        )
        self._conn.commit()
