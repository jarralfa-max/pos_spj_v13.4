"""CustomerDisplay — SET-17 "Displays": the registration of one physical
(or virtual) customer-facing second screen at a workstation. Mirrors the
shape `backend.domain.settings.entities.workstation.Workstation` and
`backend.domain.device_management.entities.device.Device` already
established for "a real thing registered at a workstation".

`current_mode` has no state-machine constraints (`_ALLOWED_FROM` sets the
way `PrintJob`/`DocumentTemplateVersion` have) — a screen's mode reflects
whatever the owning sale's status is right now, and any status can follow
any other as a sale progresses (§6/§50: Sales only publishes state here,
this bounded context never validates sale business logic), so
`set_mode()` is an unconstrained assignment, not a guarded transition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_display.enums import CustomerDisplayMode
from backend.domain.customer_display.exceptions import CustomerDisplayInvalidValueError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CustomerDisplay:
    id: str
    workstation_id: str
    name: str
    current_mode: CustomerDisplayMode = CustomerDisplayMode.IDLE
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, workstation_id: str, name: str) -> "CustomerDisplay":
        if not name.strip():
            raise CustomerDisplayInvalidValueError("name es obligatorio")
        return cls(id=new_uuid(), workstation_id=validate_uuidv7(workstation_id), name=name.strip())

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()

    def set_mode(self, mode: CustomerDisplayMode) -> None:
        self.current_mode = mode
        self._touch()
