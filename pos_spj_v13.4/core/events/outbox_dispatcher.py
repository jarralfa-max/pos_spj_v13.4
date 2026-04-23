from __future__ import annotations

import logging
import threading

from core.events.outbox import fetch_pending, mark_dispatched

logger = logging.getLogger("spj.outbox_dispatcher")


def dispatch_pending(db, bus=None, max_events: int = 100) -> dict:
    """
    Publica eventos pendientes del outbox en EventBus y marca resultado.
    Operación idempotente a nivel de estado del outbox (PENDING->DISPATCHED/ERROR).
    """
    if bus is None:
        from core.events.event_bus import get_bus
        bus = get_bus()

    pending = fetch_pending(db, limit=max_events)
    dispatched = 0
    failed = 0

    for ev in pending:
        try:
            bus.publish(ev["event_type"], ev["payload"], async_=False)
            mark_dispatched(db, ev["id"])
            dispatched += 1
        except Exception as e:
            mark_dispatched(db, ev["id"], error=str(e))
            failed += 1
            logger.error("Outbox dispatch failed id=%s type=%s: %s",
                         ev.get("id"), ev.get("event_type"), e)

    return {
        "pending": len(pending),
        "dispatched": dispatched,
        "failed": failed,
    }


class OutboxDispatcherThread(threading.Thread):
    """
    Worker periódico para despachar outbox en background.
    """
    def __init__(
        self,
        db,
        bus=None,
        interval_s: float = 2.0,
        batch_size: int = 100,
        max_batches_per_cycle: int = 20,
    ):
        super().__init__(daemon=True, name="OutboxDispatcher")
        self.db = db
        self.bus = bus
        self.interval_s = max(0.2, float(interval_s))
        self.batch_size = max(1, int(batch_size))
        self.max_batches_per_cycle = max(1, int(max_batches_per_cycle))
        self._stop_evt = threading.Event()

    def _drain_once(self) -> dict:
        summary_total = {"batches": 0, "pending": 0, "dispatched": 0, "failed": 0}
        for _ in range(self.max_batches_per_cycle):
            if self._stop_evt.is_set():
                break
            summary = dispatch_pending(self.db, bus=self.bus, max_events=self.batch_size)
            summary_total["batches"] += 1
            summary_total["pending"] = summary.get("pending", 0)
            summary_total["dispatched"] += summary.get("dispatched", 0)
            summary_total["failed"] += summary.get("failed", 0)
            if summary_total["pending"] < self.batch_size:
                break
        return summary_total

    def run(self):
        logger.info(
            "Outbox dispatcher started interval=%.2fs batch=%d max_batches=%d",
            self.interval_s,
            self.batch_size,
            self.max_batches_per_cycle,
        )
        while not self._stop_evt.is_set():
            try:
                self._drain_once()
            except Exception as e:
                logger.error("Outbox dispatcher loop error: %s", e)
            self._stop_evt.wait(self.interval_s)
        logger.info("Outbox dispatcher stopped")

    def stop(self):
        self._stop_evt.set()
