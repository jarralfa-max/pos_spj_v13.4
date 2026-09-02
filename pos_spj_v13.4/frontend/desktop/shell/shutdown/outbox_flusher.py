"""OutboxFlusher — SHELL-15.

The pluggable "actually send whatever's still queued" port
`OutboxShutdownStep` calls through. The real durable-queue tables already
exist (`sync_outbox`, `event_outbox`, `delivery_outbox_events` — see
`migrations/m000_base_schema.py`) and a legacy `sync/sync_engine.py` reads
them today, but that engine takes an integer `sucursal_id` and is not
UUIDv7-clean (REGLA CERO) — this Protocol is deliberately new and
implementation-agnostic rather than wrapping that legacy class, matching
the same "declare the port, wire the real (migrated) backend later" shape
`ModuleActivator` (SHELL-13) and `BackgroundService` (SHELL-14) use.

`flush()` returns how many items were actually sent within the timeout —
not a bool — so `OutboxShutdownStep` can report a partial flush (some
sent, some still pending) accurately rather than as a flat failure. Items
left pending are never lost: they stay in the durable outbox table and
are picked up again the next time whatever reads it runs — that's the
entire point of an outbox over an in-memory queue.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class OutboxFlusher(Protocol):
    def pending_count(self) -> int: ...
    def flush(self, *, timeout_seconds: float) -> int: ...
