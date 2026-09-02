"""AppearancePreference — SET-22 "Light/dark" + "Density": one
theme+density override at a given scope. Generalizes
`core/services/theme_service.py`'s single global `{ui_theme, ui_density}`
pair (stored as two flat keys in `configuraciones`) into per-branch/
per-user overrides — no legacy precedent for scoping at all. Mirrors
`backend.domain.feature_flags.entities.feature_flag_rule.FeatureFlagRule`
(bounded-context independence — reimplemented, not imported).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.appearance.enums import AppearanceScopeType, DensityLevel
from backend.domain.appearance.exceptions import AppearanceInvalidValueError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AppearancePreference:
    id: str
    scope_type: AppearanceScopeType
    scope_id: str | None
    theme_id: str
    density_level: DensityLevel
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, scope_type: AppearanceScopeType, scope_id: str | None, theme_id: str,
        density_level: DensityLevel = DensityLevel.NORMAL,
    ) -> "AppearancePreference":
        if scope_type is AppearanceScopeType.GLOBAL and scope_id is not None:
            raise AppearanceInvalidValueError("scope_type=GLOBAL no debe llevar scope_id")
        if scope_type is not AppearanceScopeType.GLOBAL and not scope_id:
            raise AppearanceInvalidValueError(f"scope_type={scope_type.value} requiere scope_id")
        return cls(
            id=new_uuid(), scope_type=scope_type, scope_id=scope_id, theme_id=validate_uuidv7(theme_id),
            density_level=density_level,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()

    def change_theme(self, theme_id: str) -> None:
        self.theme_id = validate_uuidv7(theme_id)
        self._touch()

    def change_density(self, density_level: DensityLevel) -> None:
        self.density_level = density_level
        self._touch()

    def matches(self, scope_type: AppearanceScopeType, scope_id: str | None) -> bool:
        return self.active and self.scope_type is scope_type and self.scope_id == scope_id
