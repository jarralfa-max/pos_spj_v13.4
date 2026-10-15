"""Update job — the journal of one install attempt, outside the database.

It lives in a file next to the data (not in SQLite) on purpose: if the update
fails after migrating and the database is restored from the backup, a row
written into that database would vanish with the restore. The application
ingests finished jobs into `software_update_events` on its next start.

States and the only legal transitions:

    STAGED ─► WAITING_FOR_APP_EXIT ─► BACKING_UP ─► INSTALLING ─► VERIFYING ─► COMPLETED
       │              │                    │             │  │          │
       └──────────────┴──► CANCELLED ◄─────┴─────────────┘  ▼          ▼
                     (INSTALLING → CANCELLED only when the  ROLLING_BACK
                      installer never started: UAC declined)
                                                     │        │
                                                     ▼        ▼
                                              ROLLED_BACK   NEEDS_RECOVERY

`NEEDS_RECOVERY` means the automatic rollback itself failed: the application
must not start normally until a person runs the guided recovery the desktop
offers at startup (restore the pre-update backup and reinstall the previous
version); when that works the job ends `RECOVERED`. `NEEDS_RECOVERY` is
"terminal" for the updater, not for the person.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class UpdateJobState(str, Enum):
    STAGED = "STAGED"
    WAITING_FOR_APP_EXIT = "WAITING_FOR_APP_EXIT"
    BACKING_UP = "BACKING_UP"
    INSTALLING = "INSTALLING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    NEEDS_RECOVERY = "NEEDS_RECOVERY"
    RECOVERED = "RECOVERED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL

    @property
    def label(self) -> str:
        return _LABELS[self]


_TERMINAL = frozenset({
    UpdateJobState.COMPLETED, UpdateJobState.ROLLED_BACK,
    UpdateJobState.NEEDS_RECOVERY, UpdateJobState.RECOVERED, UpdateJobState.CANCELLED,
})

_LABELS = {
    UpdateJobState.STAGED: "Preparada",
    UpdateJobState.WAITING_FOR_APP_EXIT: "Esperando cierre de la aplicación",
    UpdateJobState.BACKING_UP: "Respaldando base de datos",
    UpdateJobState.INSTALLING: "Instalando",
    UpdateJobState.VERIFYING: "Verificando arranque",
    UpdateJobState.COMPLETED: "Completada",
    UpdateJobState.ROLLING_BACK: "Revirtiendo",
    UpdateJobState.ROLLED_BACK: "Revertida",
    UpdateJobState.NEEDS_RECOVERY: "Requiere recuperación",
    UpdateJobState.RECOVERED: "Recuperada",
    UpdateJobState.CANCELLED: "Cancelada",
}

_TRANSITIONS: dict[UpdateJobState, frozenset[UpdateJobState]] = {
    UpdateJobState.STAGED: frozenset({UpdateJobState.WAITING_FOR_APP_EXIT,
                                      UpdateJobState.CANCELLED}),
    UpdateJobState.WAITING_FOR_APP_EXIT: frozenset({UpdateJobState.BACKING_UP,
                                                    UpdateJobState.CANCELLED}),
    UpdateJobState.BACKING_UP: frozenset({UpdateJobState.INSTALLING, UpdateJobState.CANCELLED}),
    UpdateJobState.INSTALLING: frozenset({UpdateJobState.VERIFYING,
                                          UpdateJobState.ROLLING_BACK,
                                          UpdateJobState.CANCELLED}),
    UpdateJobState.VERIFYING: frozenset({UpdateJobState.COMPLETED,
                                         UpdateJobState.ROLLING_BACK}),
    UpdateJobState.ROLLING_BACK: frozenset({UpdateJobState.ROLLED_BACK,
                                            UpdateJobState.NEEDS_RECOVERY}),
    # A person ran the guided recovery (restore + previous version) and the
    # previous version started again.
    UpdateJobState.NEEDS_RECOVERY: frozenset({UpdateJobState.RECOVERED}),
}


class IllegalUpdateTransitionError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class UpdateJobStep:
    state: UpdateJobState
    at: str
    detail: str = ""


@dataclass(frozen=True)
class UpdateJob:
    job_id: str
    operation_id: str
    from_version: str
    to_version: str
    channel: str
    installer_path: str
    installer_sha256: str
    installer_size: int
    database_path: str
    workstation_id: str
    branch_id: str
    requested_by: str
    offline: bool = False
    previous_installer_path: str = ""
    backup_path: str = ""
    state: UpdateJobState = UpdateJobState.STAGED
    history: tuple[UpdateJobStep, ...] = field(default_factory=tuple)
    migrations_may_have_run: bool = False
    #: "" = install right away; "HH:MM-HH:MM" = wait for that window.
    scheduled_window: str = ""
    #: Set when the job is created by the in-app scheduler.
    created_at: str = ""

    def transition(self, target: UpdateJobState, detail: str = "", **changes: Any) -> "UpdateJob":
        if target not in _TRANSITIONS.get(self.state, frozenset()):
            raise IllegalUpdateTransitionError(
                f"Transición no permitida: {self.state.value} → {target.value}")
        step = UpdateJobStep(state=target, at=_now(), detail=detail)
        return replace(self, state=target, history=self.history + (step,), **changes)

    def annotate(self, detail: str) -> "UpdateJob":
        """Record something that happened without changing state (e.g. a
        recovery attempt that did not succeed)."""
        step = UpdateJobStep(state=self.state, at=_now(), detail=detail)
        return replace(self, history=self.history + (step,))

    @property
    def last_detail(self) -> str:
        return self.history[-1].detail if self.history else ""

    def to_dict(self) -> dict[str, Any]:
        data = {name: getattr(self, name) for name in self.__dataclass_fields__}
        data["state"] = self.state.value
        data["history"] = [
            {"state": s.state.value, "at": s.at, "detail": s.detail} for s in self.history]
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "UpdateJob":
        values = dict(data)
        values["state"] = UpdateJobState(values["state"])
        values["history"] = tuple(
            UpdateJobStep(state=UpdateJobState(s["state"]), at=s["at"], detail=s.get("detail", ""))
            for s in values.get("history") or ())
        known = cls.__dataclass_fields__
        return cls(**{key: value for key, value in values.items() if key in known})
