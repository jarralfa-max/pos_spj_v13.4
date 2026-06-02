from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

logger = logging.getLogger("spj.delivery.application.outbox")


class ProcessDeliveryOutboxUseCase:
    """Processes pending delivery outbox events with controlled retries."""

    def __init__(
        self,
        *,
        outbox_repository,
        handlers: Mapping[str, Callable[[dict[str, Any]], None]] | None = None,
        publisher: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.outbox_repository = outbox_repository
        self.handlers = dict(handlers or {})
        self.publisher = publisher

    def execute(self, *, limit: int = 50) -> dict[str, int]:
        processed = 0
        failed = 0
        for event in self.outbox_repository.fetch_pending(limit=limit):
            event_id = int(event["id"])
            event_type = str(event["event_type"])
            payload = event.get("payload") or {}
            try:
                handler = self.handlers.get(event_type)
                if handler is not None:
                    handler(payload)
                elif self.publisher is not None:
                    self.publisher(event_type, payload)
                else:
                    raise RuntimeError(f"No hay handler registrado para {event_type}")
                self.outbox_repository.mark_done(event_id)
                processed += 1
            except Exception as exc:
                logger.warning("delivery outbox event failed id=%s type=%s: %s", event_id, event_type, exc)
                self.outbox_repository.mark_error(event_id, str(exc))
                failed += 1
        return {"processed": processed, "failed": failed}
