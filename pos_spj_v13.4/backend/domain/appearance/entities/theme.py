"""Theme — SET-22 "Themes": the catalog entry for one installable UI
theme. Generalizes the legacy `ui/themes/theme_engine.py` hardcoded
`"Claro"/"Oscuro"` pair (and its `SPJ_LIGHT`/`SPJ_DARK` aliases) into a
typed, admin-managed catalog — `mode` carries the light/dark split
(§22 "Light/dark"), `is_default` replaces the legacy service's hardcoded
`{'theme': 'Oscuro'}` fallback with real, queryable data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.appearance.enums import ThemeMode
from backend.domain.appearance.exceptions import AppearanceInvalidValueError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Theme:
    id: str
    code: str
    name: str
    mode: ThemeMode
    active: bool = True
    is_default: bool = False
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, code: str, name: str, mode: ThemeMode, is_default: bool = False,
    ) -> "Theme":
        if not code.strip():
            raise AppearanceInvalidValueError("code es obligatorio")
        if not name.strip():
            raise AppearanceInvalidValueError("name es obligatorio")
        return cls(
            id=new_uuid(), code=code.strip(), name=name.strip(), mode=mode, is_default=bool(is_default),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def update_details(self, *, name: str) -> None:
        if not name.strip():
            raise AppearanceInvalidValueError("name es obligatorio")
        self.name = name.strip()
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()

    def mark_default(self) -> None:
        self.is_default = True
        self._touch()

    def unmark_default(self) -> None:
        self.is_default = False
        self._touch()
