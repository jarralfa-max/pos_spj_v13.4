"""WorkersShutdownStep — SHELL-15.

Stops every bound `BackgroundService` via `BackgroundServiceSupervisor.stop_all()`
(SHELL-14). `stop_all()` already isolates per-service failures — a service
that raises out of its own `stop()` never blocks the others from stopping
— so this step only has to summarize the results, not implement that
isolation itself. Meant to run *first* in the coordinator's step list:
workers are the most likely thing still touching a DB connection or
producing outbox items, so they need to be quiet before the outbox flush
or connection close can be considered complete.
"""
from __future__ import annotations

from frontend.desktop.shell.background.background_service_supervisor import BackgroundServiceSupervisor
from frontend.desktop.shell.shutdown.shutdown_context import ShutdownContext
from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepResult


class WorkersShutdownStep:
    name = "workers"

    def __init__(self, supervisor: BackgroundServiceSupervisor) -> None:
        self._supervisor = supervisor

    def run(self, context: ShutdownContext) -> ShutdownStepResult:
        results = self._supervisor.stop_all()
        if not results:
            return ShutdownStepResult.ok(self.name, "No hay servicios en segundo plano vinculados.")

        failed = {service_id: error for service_id, error in results.items() if error is not None}
        if failed:
            names = ", ".join(sorted(failed))
            return ShutdownStepResult.warning(
                self.name,
                f"{len(failed)} de {len(results)} servicio(s) no se detuvieron limpiamente: {names}.",
            )
        return ShutdownStepResult.ok(self.name, f"Se detuvieron {len(results)} servicio(s) en segundo plano.")
