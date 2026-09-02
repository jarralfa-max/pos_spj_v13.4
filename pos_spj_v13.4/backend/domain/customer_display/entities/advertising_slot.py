"""AdvertisingSlot — SET-18 "Placements": a named zone on a
`CustomerDisplayMode` screen where a `ContentCampaign` can be shown (e.g.
an "IDLE_MAIN_BANNER" slot exists for `CustomerDisplayMode.IDLE`).
Reuses `CustomerDisplayMode` directly — same bounded context as
`CustomerDisplay`/`DisplayLayout` (SET-17), not a cross-context import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_display.enums import CustomerDisplayMode
from backend.domain.customer_display.exceptions import CustomerDisplayInvalidValueError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AdvertisingSlot:
    id: str
    code: str
    mode: CustomerDisplayMode
    display_order: int = 0
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, code: str, mode: CustomerDisplayMode, display_order: int = 0,
    ) -> "AdvertisingSlot":
        if not code.strip():
            raise CustomerDisplayInvalidValueError("code es obligatorio")
        if isinstance(display_order, bool) or not isinstance(display_order, int) or display_order < 0:
            raise CustomerDisplayInvalidValueError(
                f"display_order debe ser un entero >= 0, recibido {display_order!r}"
            )
        return cls(id=new_uuid(), code=code.strip().upper(), mode=mode, display_order=display_order)

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()

    def update_display_order(self, order: int) -> None:
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            raise CustomerDisplayInvalidValueError(f"order debe ser un entero >= 0, recibido {order!r}")
        self.display_order = order
        self._touch()
