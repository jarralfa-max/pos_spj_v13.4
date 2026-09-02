"""FeatureFlag — SET-21 "Flags": the catalog entry for one togglable ERP
capability. Generalizes the bare string keys
`core/services/feature_flag_service.py::is_enabled(feature_name, ...)`
already uses in production (`'delivery_auto_asign'`, module codes from
`modulos/config_modules.py::MODULOS_SISTEMA`) into a typed, admin-managed
catalog with a real `default_enabled` fallback — the legacy service's
`is_enabled()` silently defaults an unknown flag to `False`
("por seguridad asumimos que está apagado"); this makes that default
explicit, per-flag data instead of a single hardcoded assumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.feature_flags.exceptions import FeatureFlagsInvalidValueError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class FeatureFlag:
    id: str
    code: str
    name: str
    description: str = ""
    default_enabled: bool = False
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, code: str, name: str, description: str = "", default_enabled: bool = False,
    ) -> "FeatureFlag":
        if not code.strip():
            raise FeatureFlagsInvalidValueError("code es obligatorio")
        if not name.strip():
            raise FeatureFlagsInvalidValueError("name es obligatorio")
        return cls(
            id=new_uuid(), code=code.strip(), name=name.strip(), description=description.strip(),
            default_enabled=bool(default_enabled),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def update_details(self, *, name: str, description: str = "", default_enabled: bool = False) -> None:
        if not name.strip():
            raise FeatureFlagsInvalidValueError("name es obligatorio")
        self.name = name.strip()
        self.description = description.strip()
        self.default_enabled = bool(default_enabled)
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()
