# infrastructure/persistence/sqlite_quote_draft_repository.py — WA-11
"""Implementación SQLite de `WhatsAppQuoteDraftRepository` contra
`whatsapp_quote_drafts`/`whatsapp_quote_draft_lines` (migración 245)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from domain.whatsapp.entities.order_draft import OrderDraftLine
from domain.whatsapp.entities.quote_draft import QuoteDraft
from domain.whatsapp.enums import QuoteDraftStatus

_DRAFT_COLUMNS = (
    "id, conversation_id, branch_id, customer_external_id, quote_external_id, "
    "folio, status, created_at, updated_at"
)
_LINE_COLUMNS = "id, draft_id, product_external_id, product_name, quantity, unit, unit_price"


class SqliteWhatsAppQuoteDraftRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_id(self, draft_id: str) -> Optional[QuoteDraft]:
        row = self._conn.execute(
            f"SELECT {_DRAFT_COLUMNS} FROM whatsapp_quote_drafts WHERE id=?", (draft_id,)
        ).fetchone()
        return self._draft_from_row(row) if row else None

    def get_active_for_conversation(self, conversation_id: str) -> Optional[QuoteDraft]:
        row = self._conn.execute(
            f"SELECT {_DRAFT_COLUMNS} FROM whatsapp_quote_drafts "
            "WHERE conversation_id=? AND status IN ('CAPTURING','CREATED') "
            "ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        return self._draft_from_row(row) if row else None

    def save(self, draft: QuoteDraft) -> None:
        self._conn.execute(
            "INSERT INTO whatsapp_quote_drafts "
            f"({_DRAFT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "branch_id=excluded.branch_id, "
            "customer_external_id=excluded.customer_external_id, "
            "quote_external_id=excluded.quote_external_id, "
            "folio=excluded.folio, "
            "status=excluded.status, "
            "updated_at=excluded.updated_at",
            (
                draft.id,
                draft.conversation_id,
                draft.branch_id,
                draft.customer_external_id,
                draft.quote_external_id,
                draft.folio,
                draft.status.value,
                draft.created_at.isoformat(),
                draft.updated_at.isoformat(),
            ),
        )
        self._conn.execute("DELETE FROM whatsapp_quote_draft_lines WHERE draft_id=?", (draft.id,))
        for line in draft.lines:
            self._conn.execute(
                f"INSERT INTO whatsapp_quote_draft_lines ({_LINE_COLUMNS}) VALUES (?,?,?,?,?,?,?)",
                (line.id, draft.id, line.product_external_id, line.product_name, line.quantity, line.unit, line.unit_price),
            )
        self._conn.commit()

    def _draft_from_row(self, row) -> QuoteDraft:
        lines = [
            OrderDraftLine(
                id=r[0], product_external_id=r[2], product_name=r[3],
                quantity=r[4], unit=r[5], unit_price=r[6],
            )
            for r in self._conn.execute(
                f"SELECT {_LINE_COLUMNS} FROM whatsapp_quote_draft_lines WHERE draft_id=?", (row[0],)
            ).fetchall()
        ]
        return QuoteDraft(
            id=row[0],
            conversation_id=row[1],
            branch_id=row[2],
            customer_external_id=row[3],
            quote_external_id=row[4],
            folio=row[5],
            status=QuoteDraftStatus(row[6]),
            lines=lines,
            created_at=datetime.fromisoformat(row[7]),
            updated_at=datetime.fromisoformat(row[8]),
        )
