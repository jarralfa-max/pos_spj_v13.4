"""SalesOutboxRepository — persistence for the transactional outbox
(`sales_outbox`, created in SALES-4). Mirrors
backend/infrastructure/db/repositories/inventory/support_repositories.py's
`InventoryOutboxRepository` exactly.

No dispatcher exists yet for this bounded context (deliberately — see
docs/refactor/SALES-4_esquema_limpio.md: the one rich reference
implementation, `InventoryOutboxDispatcher`, is confirmed dead code in this
repo too, never instantiated by any real app entrypoint). This repository
only provides the enqueue/read/mark-dispatched primitives a future
dispatcher (or a direct EventBus bridge) would need.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.sales.base import SalesRepositoryBase, now_iso
from backend.shared.ids import new_uuid


class SalesOutboxRepository(SalesRepositoryBase):
    def enqueue(self, *, event_id: str, event_name: str, payload_json: str,
                operation_id: str) -> None:
        self._execute(
            "INSERT INTO sales_outbox (id, event_id, event_name, payload_json,"
            " operation_id, status, created_at) VALUES (?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id, now_iso()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id, created_at"
            " FROM sales_outbox WHERE status='PENDING' ORDER BY created_at LIMIT ?",
            (limit,))

    def get_by_event_id(self, event_id: str) -> dict | None:
        return self._query_one(
            "SELECT id, event_id, event_name, payload_json, operation_id, status"
            " FROM sales_outbox WHERE event_id=?", (event_id,))

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE sales_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (now_iso(), outbox_id))
