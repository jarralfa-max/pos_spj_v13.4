"""Before the database is opened: is an update running, interrupted, or in
need of a person's recovery?

* IN_PROGRESS — the external updater is alive (it holds its lock): the
  desktop must not open the database; it says so and exits.
* NEEDS_RECOVERY — the automatic rollback failed, or the updater died while
  installing/verifying (power cut, killed process). The desktop does not
  start normally; it offers the guided recovery.
* An updater that died BEFORE installing (waiting for exit, backing up)
  changed nothing: the job is closed as CANCELLED and the start continues.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from backend.domain.software_distribution.update_job import UpdateJob, UpdateJobState


class GateKind(str, Enum):
    CLEAR = "CLEAR"
    IN_PROGRESS = "IN_PROGRESS"
    NEEDS_RECOVERY = "NEEDS_RECOVERY"


@dataclass(frozen=True)
class StartupGateResult:
    kind: GateKind
    job: UpdateJob | None = None
    message: str = ""


class _Store(Protocol):
    def load(self) -> UpdateJob | None: ...
    def save(self, job: UpdateJob) -> UpdateJob: ...


class _Probe(Protocol):
    def acquire(self, *, timeout_seconds: float = 0.0, poll_seconds: float = 0.25) -> bool: ...
    def release(self) -> None: ...


_UNTOUCHED = frozenset({UpdateJobState.WAITING_FOR_APP_EXIT, UpdateJobState.BACKING_UP})
_MID_INSTALL = frozenset({UpdateJobState.INSTALLING, UpdateJobState.VERIFYING,
                          UpdateJobState.ROLLING_BACK})


class UpdateStartupGate:
    def __init__(self, job_store: _Store, updater_lock: _Probe) -> None:
        self._store = job_store
        self._updater_lock = updater_lock

    def inspect(self) -> StartupGateResult:
        try:
            job = self._store.load()
        except (OSError, ValueError) as exc:
            # An unreadable journal must not keep a till closed; it is logged
            # by the caller and the start continues.
            return StartupGateResult(GateKind.CLEAR, None, f"Diario ilegible: {exc}")
        if job is None:
            return StartupGateResult(GateKind.CLEAR)
        if job.state is UpdateJobState.NEEDS_RECOVERY:
            return StartupGateResult(GateKind.NEEDS_RECOVERY, job, job.last_detail)
        if job.state.is_terminal or job.state is UpdateJobState.STAGED:
            return StartupGateResult(GateKind.CLEAR, job)

        if not self._updater_lock.acquire(timeout_seconds=0):
            return StartupGateResult(
                GateKind.IN_PROGRESS, job,
                f"Se está instalando la versión {job.to_version} ({job.state.label}). "
                "Espere a que termine; la aplicación se abrirá sola.")
        self._updater_lock.release()

        if job.state in _UNTOUCHED:
            job = self._store.save(job.transition(
                UpdateJobState.CANCELLED,
                f"El actualizador se detuvo durante «{job.state.label}»; no se instaló nada."))
            return StartupGateResult(GateKind.CLEAR, job)
        if job.state in _MID_INSTALL:
            stage = job.state.label
            if job.state is not UpdateJobState.ROLLING_BACK:
                job = job.transition(UpdateJobState.ROLLING_BACK,
                                     f"El actualizador se interrumpió durante «{stage}».")
            job = self._store.save(job.transition(
                UpdateJobState.NEEDS_RECOVERY,
                f"La actualización a {job.to_version} se interrumpió durante «{stage}». "
                "Ejecute la recuperación guiada."))
            return StartupGateResult(GateKind.NEEDS_RECOVERY, job, job.last_detail)
        return StartupGateResult(GateKind.CLEAR, job)
