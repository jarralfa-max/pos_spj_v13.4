# infrastructure/persistence/sqlite_order_draft_repository.py — WA-10
"""Implementación SQLite de `WhatsAppOrderDraftRepository` contra
`whatsapp_order_drafts`/`whatsapp_order_draft_lines` (migración 244)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from decimal import Decimal

from domain.whatsapp.entities.order_draft import OrderDraft, OrderDraftLine
from domain.whatsapp.enums import DeliveryMethod, OrderDraftStatus

_DRAFT_COLUMNS = (
    "id, conversation_id, branch_id, customer_external_id, delivery_method, "
    "status, created_at, updated_at"
)
_LINE_COLUMNS = "id, draft_id, product_external_id, product_name, quantity, unit, unit_price"


class SqliteWhatsAppOrderDraftRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_id(self, draft_id: str) -> Optional[OrderDraft]:
        row = self._conn.execute(
            f"SELECT {_DRAFT_COLUMNS} FROM whatsapp_order_drafts WHERE id=?", (draft_id,)
        ).fetchone()
        return self._draft_from_row(row) if row else None

    def get_active_for_conversation(self, conversation_id: str) -> Optional[OrderDraft]:
        row = self._conn.execute(
            f"SELECT {_DRAFT_COLUMNS} FROM whatsapp_order_drafts "
            "WHERE conversation_id=? AND status IN ('BUILDING','AWAITING_CONFIRMATION') "
            "ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        return self._draft_from_row(row) if row else None

    def save(self, draft: OrderDraft) -> None:
        self._conn.execute(
            "INSERT INTO whatsapp_order_drafts "
            f"({_DRAFT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "branch_id=excluded.branch_id, "
            "customer_external_id=excluded.customer_external_id, "
            "delivery_method=excluded.delivery_method, "
            "status=excluded.status, "
            "updated_at=excluded.updated_at",
            (
                draft.id,
                draft.conversation_id,
                draft.branch_id,
                draft.customer_external_id,
                draft.delivery_method.value if draft.delivery_method else None,
                draft.status.value,
                draft.created_at.isoformat(),
                draft.updated_at.isoformat(),
            ),
        )
        self._conn.execute("DELETE FROM whatsapp_order_draft_lines WHERE draft_id=?", (draft.id,))
        for line in draft.lines:
            self._conn.execute(
                f"INSERT INTO whatsapp_order_draft_lines ({_LINE_COLUMNS}) VALUES (?,?,?,?,?,?,?)",
                (line.id, draft.id, line.product_external_id, line.product_name, str(line.quantity), line.unit, str(line.unit_price)),
            )
        self._conn.commit()

    def _draft_from_row(self, row) -> OrderDraft:
        lines = [
            OrderDraftLine(
                id=r[0], product_external_id=r[2], product_name=r[3],
                quantity=Decimal(r[4]), unit=r[5], unit_price=Decimal(r[6]),
            )
            for r in self._conn.execute(
                f"SELECT {_LINE_COLUMNS} FROM whatsapp_order_draft_lines WHERE draft_id=?", (row[0],)
            ).fetchall()
        ]
        return OrderDraft(
            id=row[0],
            conversation_id=row[1],
            branch_id=row[2],
            customer_external_id=row[3],
            delivery_method=DeliveryMethod(row[4]) if row[4] else None,
            status=OrderDraftStatus(row[5]),
            lines=lines,
            created_at=datetime.fromisoformat(row[6]),
            updated_at=datetime.fromisoformat(row[7]),
        )
