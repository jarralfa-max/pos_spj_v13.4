"""LoyaltyOutboxRepository — persistence for the transactional outbox
(`loyalty_outbox`, created in LOY-3). Mirrors
backend/infrastructure/db/repositories/sales/outbox_repository.py exactly.

No dispatcher exists yet for this bounded context — deliberate, see
docs/refactor/LOY-2_dominio_base.md: the one rich reference implementation,
`InventoryOutboxDispatcher`, is confirmed dead code in this repo too, never
instantiated by any real app entrypoint. This repository only provides the
enqueue/read/mark-dispatched primitives a future dispatcher (or a direct
EventBus bridge, mirroring `core/events/handlers/finance_handler.py`'s
pattern) would need.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.loyalty.base import LoyaltyRepositoryBase, now_iso
from backend.shared.ids import new_uuid


class LoyaltyOutboxRepository(LoyaltyRepositoryBase):
    def enqueue(self, *, event_id: str, event_name: str, payload_json: str,
                operation_id: str) -> None:
        self._execute(
            "INSERT INTO loyalty_outbox (id, event_id, event_name, payload_json,"
            " operation_id, status, created_at) VALUES (?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id, now_iso()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id, created_at"
            " FROM loyalty_outbox WHERE status='PENDING' ORDER BY created_at LIMIT ?",
            (limit,))

    def get_by_event_id(self, event_id: str) -> dict | None:
        return self._query_one(
            "SELECT id, event_id, event_name, payload_json, operation_id, status"
            " FROM loyalty_outbox WHERE event_id=?", (event_id,))

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE loyalty_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (now_iso(), outbox_id))
