"""ConnectionsShutdownStep — SHELL-15.

Closes every open database connection (via `ConnectionCloser`, see its
docstring). Meant to run *last* in the coordinator's step list — workers
must be quiet and the outbox flushed before it's safe to close what they
might still be using.
"""
from __future__ import annotations

from frontend.desktop.shell.shutdown.connection_closer import ConnectionCloser
from frontend.desktop.shell.shutdown.shutdown_context import ShutdownContext
from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepResult


class ConnectionsShutdownStep:
    name = "connections"

    def __init__(self, connection_closer: ConnectionCloser) -> None:
        self._closer = connection_closer

    def run(self, context: ShutdownContext) -> ShutdownStepResult:
        try:
            closed = self._closer.close_all()
        except Exception as exc:  # noqa: BLE001 - a broken close must not abort the remaining steps
            return ShutdownStepResult.failed(
                self.name, f"No se pudieron cerrar todas las conexiones: {exc}", exception=exc,
            )
        return ShutdownStepResult.ok(self.name, f"Se cerraron {closed} conexión(es).")
