"""InventoryEventIngestor — idempotent inbound apply for synced events (§59).

The receiving side of offline-first sync and the conflict-resolution rule: an
event is applied at most once, keyed by its ``event_id``. A duplicate that
arrives from a replayed outbox or a re-sent batch is recognized and skipped, so
concurrent/retried delivery never double-applies. The caller supplies the effect
(``apply_fn``); the ingestor owns the dedupe + processed-registry bookkeeping,
committed atomically with the effect.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


class InventoryEventIngestor:
    def __init__(self, connection) -> None:
        self._conn = connection

    def ingest(self, event: dict, apply_fn=None) -> bool:
        """Apply ``event`` once. Returns True if applied, False if it was a
        duplicate (already processed). ``apply_fn(event, uow)`` runs the effect
        inside the same transaction as the processed-registry write."""
        event_id = str(event.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("El evento a ingerir requiere event_id")
        with InventoryUnitOfWork(self._conn) as uow:
            if uow.processed_events.was_processed(event_id):
                return False
            if apply_fn is not None:
                apply_fn(event, uow)
            uow.processed_events.mark_processed(
                event_id, str(event.get("event_name") or ""),
                str(event.get("operation_id") or ""))
        return True
