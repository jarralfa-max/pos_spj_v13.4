"""OutboxShutdownStep — SHELL-15.

Flushes whatever's pending in the outbox (via `OutboxFlusher`, see its
docstring) before the app closes its DB connections. Items that don't make
it out within `timeout_seconds` are never lost — they're durable, sitting
in the outbox table until the next launch retries them — so a partial
flush is a `WARNING`, not a `FAILED`: shutdown itself isn't broken, it's
just deferring some work. Only an actual exception from `flush()` counts
as `FAILED`. Meant to run *after* `WorkersShutdownStep` (nothing should
still be writing to the outbox) and *before* `ConnectionsShutdownStep`
(flushing needs a live DB connection to read/update the outbox table).
"""
from __future__ import annotations

from frontend.desktop.shell.shutdown.outbox_flusher import OutboxFlusher
from frontend.desktop.shell.shutdown.shutdown_context import ShutdownContext
from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepResult


class OutboxShutdownStep:
    name = "outbox"

    def __init__(self, outbox: OutboxFlusher, *, timeout_seconds: float = 10.0) -> None:
        self._outbox = outbox
        self._timeout_seconds = timeout_seconds

    def run(self, context: ShutdownContext) -> ShutdownStepResult:
        try:
            pending_before = self._outbox.pending_count()
            if pending_before == 0:
                return ShutdownStepResult.ok(self.name, "No hay elementos pendientes en el outbox.")
            flushed = self._outbox.flush(timeout_seconds=self._timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - a broken flush must not abort the remaining steps
            return ShutdownStepResult.failed(
                self.name, f"El vaciado del outbox falló con una excepción: {exc}", exception=exc,
            )

        remaining = pending_before - flushed
        if remaining > 0:
            return ShutdownStepResult.warning(
                self.name,
                f"{remaining} de {pending_before} elemento(s) quedaron pendientes "
                f"(se reintentarán en el próximo inicio).",
            )
        return ShutdownStepResult.ok(self.name, f"Se enviaron {flushed} elemento(s) pendiente(s).")
