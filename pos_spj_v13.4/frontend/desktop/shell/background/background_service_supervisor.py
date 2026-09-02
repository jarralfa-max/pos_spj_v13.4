"""BackgroundServiceSupervisor — SHELL-14.

Owns the running lifecycle of every bound `BackgroundService`: starting
them (`start()`/`start_all()`), stopping them (`stop()`), and — the
distinctive part — reacting to crashes via `RestartPolicy` instead of
retrying blindly or giving up after the first failure.

Two ways a crash reaches the supervisor:
- Synchronously, when `start()`/a restart attempt's `instance.start()`
  call itself raises.
- Asynchronously, via `notify_crashed()` — a running service has no way to
  signal a later failure through the `BackgroundService` Protocol alone
  (see its docstring), so it's expected to call this itself.

Both paths converge on the same `RestartPolicy` decision: `_maybe_restart()`
asks `next_restart_delay_seconds()` and either schedules a retry (state
`RESTARTING`, via the injected `scheduler` — a `QTimer`-based one in
production, `immediate_restart_scheduler` — the default — everywhere that
doesn't need real deferred timing) or gives up (state `FAILED`) once the
policy says so.

A deliberate `start()` call (initial start, or a manual restart of a
`FAILED` service) resets that service's crash history first — the
restart-policy budget bounds *automatic* retries after a crash, not
intentional restarts a caller explicitly asked for. `stop()` does the
same, so a service stopped and later started again gets a clean slate. A
successful `start()`/restart also clears `last_error` — otherwise
`status_of().last_error` would keep reporting a stale error from a crash
the service has since recovered from.

`stop()` never lets `instance.stop()` raising prevent the state
transition to `STOPPED`, or (SHELL-15) block stopping every *other* bound
service — it catches the exception, records it, and returns it so a
caller (e.g. `WorkersShutdownStep`) can tell a clean stop from a dirty one
without relying on possibly-stale supervisor state.

Health reporting deliberately does **not** implement SHELL-3's `HealthCheck`
Protocol — that Protocol's `check()` takes a `BootstrapContext`
("bootstrap-time plumbing," per its own docstring, never resolved
application services), and this supervisor is a runtime, post-boot
concept with nothing meaningful to put there. `health_checks()`/`health_report()`
instead build the same `HealthCheckResult`/`HealthReport` *value types*
directly — reusing the data shape SHELL-3 already established, not its
boot-sequence-scoped Protocol. `NOT_STARTED`/`STOPPED` services are
excluded from the report entirely: neither one is a health problem, it's
just "not currently expected to be running."
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from backend.bootstrap.health.health_status import HealthCheckResult, HealthReport, HealthStatus, worse_of
from frontend.desktop.shell.background.background_service import BackgroundService
from frontend.desktop.shell.background.background_service_registry import BackgroundServiceRegistry
from frontend.desktop.shell.background.background_service_state import BackgroundServiceState
from frontend.desktop.shell.background.background_service_status import BackgroundServiceStatus
from frontend.desktop.shell.background.errors import ServiceInstanceNotBoundError
from frontend.desktop.shell.background.restart_policy import RestartPolicy
from frontend.desktop.shell.background.service_crash import ServiceCrash

RestartScheduler = Callable[[Callable[[], None], float], None]

_HEALTH_STATUS_BY_STATE = {
    BackgroundServiceState.RUNNING: HealthStatus.HEALTHY,
    BackgroundServiceState.STARTING: HealthStatus.DEGRADED,
    BackgroundServiceState.CRASHED: HealthStatus.DEGRADED,
    BackgroundServiceState.RESTARTING: HealthStatus.DEGRADED,
    BackgroundServiceState.FAILED: HealthStatus.UNHEALTHY,
}


def immediate_restart_scheduler(task: Callable[[], None], delay_seconds: float) -> None:
    task()


class BackgroundServiceSupervisor:
    def __init__(
        self, *,
        registry: BackgroundServiceRegistry,
        restart_policy: Optional[RestartPolicy] = None,
        scheduler: RestartScheduler = immediate_restart_scheduler,
    ) -> None:
        self._registry = registry
        self._restart_policy = restart_policy or RestartPolicy()
        self._scheduler = scheduler
        self._instances: dict[str, BackgroundService] = {}
        self._state: dict[str, BackgroundServiceState] = {}
        self._crashes: dict[str, list[ServiceCrash]] = {}
        self._last_error: dict[str, BaseException] = {}
        self._started_at: dict[str, datetime] = {}

    def bind(self, service_id: str, instance: BackgroundService) -> None:
        self._registry.require(service_id)
        self._instances[service_id] = instance

    def is_bound(self, service_id: str) -> bool:
        return service_id in self._instances

    def state_of(self, service_id: str) -> BackgroundServiceState:
        return self._state.get(service_id, BackgroundServiceState.NOT_STARTED)

    def status_of(self, service_id: str) -> BackgroundServiceStatus:
        return BackgroundServiceStatus(
            service_id=service_id, state=self.state_of(service_id),
            crashes=tuple(self._crashes.get(service_id, ())),
            last_error=self._last_error.get(service_id), started_at=self._started_at.get(service_id),
        )

    def start(self, service_id: str) -> None:
        self._registry.require(service_id)
        instance = self._instances.get(service_id)
        if instance is None:
            raise ServiceInstanceNotBoundError(
                f"'{service_id}' no tiene una instancia de servicio vinculada — use bind() primero."
            )
        self._crashes[service_id] = []
        self._set_state(service_id, BackgroundServiceState.STARTING)
        try:
            instance.start()
        except Exception as exc:  # noqa: BLE001 - a failed start is a crash, handled uniformly
            self.notify_crashed(service_id, exc)
            return
        self._started_at[service_id] = datetime.now(timezone.utc)
        self._last_error.pop(service_id, None)
        self._set_state(service_id, BackgroundServiceState.RUNNING)

    def start_all(self) -> None:
        for descriptor in self._registry.all():
            if self.is_bound(descriptor.service_id):
                self.start(descriptor.service_id)

    def stop(self, service_id: str) -> BaseException | None:
        instance = self._instances.get(service_id)
        stop_error: BaseException | None = None
        if instance is not None:
            try:
                instance.stop()
            except Exception as exc:  # noqa: BLE001 - a failed stop must not block stopping other services
                stop_error = exc
        self._crashes[service_id] = []
        if stop_error is not None:
            self._last_error[service_id] = stop_error
        else:
            self._last_error.pop(service_id, None)
        self._set_state(service_id, BackgroundServiceState.STOPPED)
        return stop_error

    def stop_all(self) -> dict[str, BaseException | None]:
        results: dict[str, BaseException | None] = {}
        for descriptor in self._registry.all():
            if self.is_bound(descriptor.service_id):
                results[descriptor.service_id] = self.stop(descriptor.service_id)
        return results

    def notify_crashed(self, service_id: str, error: BaseException, *, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        crash = ServiceCrash(service_id=service_id, occurred_at=now, error=error)
        self._crashes.setdefault(service_id, []).append(crash)
        self._last_error[service_id] = error
        self._maybe_restart(service_id, now=now)

    def health_checks(self) -> tuple[HealthCheckResult, ...]:
        results = []
        for descriptor in self._registry.all():
            state = self.state_of(descriptor.service_id)
            status = _HEALTH_STATUS_BY_STATE.get(state)
            if status is None:
                continue
            results.append(HealthCheckResult(
                check_name=f"background_service.{descriptor.service_id}",
                status=status, message=self._health_message(descriptor.service_id),
            ))
        return tuple(results)

    def health_report(self) -> HealthReport:
        checks = self.health_checks()
        overall = HealthStatus.HEALTHY
        for check in checks:
            overall = worse_of(overall, check.status)
        return HealthReport(overall_status=overall, checks=checks, generated_at=datetime.now(timezone.utc))

    def _maybe_restart(self, service_id: str, *, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        delay = self._restart_policy.next_restart_delay_seconds(self._crashes.get(service_id, []), now=now)
        if delay is None:
            self._set_state(service_id, BackgroundServiceState.FAILED)
            return
        self._set_state(service_id, BackgroundServiceState.RESTARTING)
        self._scheduler(lambda: self._attempt_restart(service_id), delay)

    def _attempt_restart(self, service_id: str) -> None:
        instance = self._instances.get(service_id)
        if instance is None:
            return
        self._set_state(service_id, BackgroundServiceState.STARTING)
        try:
            instance.start()
        except Exception as exc:  # noqa: BLE001 - a failed restart is itself a crash
            self.notify_crashed(service_id, exc)
            return
        self._started_at[service_id] = datetime.now(timezone.utc)
        self._last_error.pop(service_id, None)
        self._set_state(service_id, BackgroundServiceState.RUNNING)

    def _set_state(self, service_id: str, state: BackgroundServiceState) -> None:
        self._state[service_id] = state

    def _health_message(self, service_id: str) -> str:
        error = self._last_error.get(service_id)
        return str(error) if error is not None else ""
