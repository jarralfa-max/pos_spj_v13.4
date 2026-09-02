"""DensityProfile — SET-22 "Density": the concrete metrics behind one
`DensityLevel`. No legacy precedent at all — `core/services/
theme_service.py`'s `density` preference is a free string
(`'Normal'` default) with no defined set of options and no metrics
attached to it. `scale_factor` is Decimal-precision-safe (persisted and
compared as `Decimal`, never `float` — REGLA general de este repo para
valores numéricos de negocio), even though it is a UI scale rather than
money, to stay consistent with the rest of the codebase's numeric
conventions and avoid float rounding drift across repeated UI reflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.appearance.enums import DensityLevel
from backend.domain.appearance.exceptions import AppearanceInvalidValueError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DensityProfile:
    id: str
    level: DensityLevel
    name: str
    scale_factor: Decimal
    control_height_px: int
    touch_target_px: int
    spacing_unit_px: int
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @staticmethod
    def _validate(
        *, name: str, scale_factor: Decimal, control_height_px: int, touch_target_px: int,
        spacing_unit_px: int,
    ) -> None:
        if not name.strip():
            raise AppearanceInvalidValueError("name es obligatorio")
        if not isinstance(scale_factor, Decimal) or scale_factor <= 0:
            raise AppearanceInvalidValueError("scale_factor debe ser un Decimal mayor a cero")
        for label, value in (
            ("control_height_px", control_height_px), ("touch_target_px", touch_target_px),
            ("spacing_unit_px", spacing_unit_px),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise AppearanceInvalidValueError(f"{label} debe ser un entero positivo, recibido {value!r}")

    @classmethod
    def create(
        cls, *, level: DensityLevel, name: str, scale_factor: Decimal, control_height_px: int,
        touch_target_px: int, spacing_unit_px: int,
    ) -> "DensityProfile":
        cls._validate(
            name=name, scale_factor=scale_factor, control_height_px=control_height_px,
            touch_target_px=touch_target_px, spacing_unit_px=spacing_unit_px,
        )
        return cls(
            id=new_uuid(), level=level, name=name.strip(), scale_factor=scale_factor,
            control_height_px=control_height_px, touch_target_px=touch_target_px,
            spacing_unit_px=spacing_unit_px,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def update_details(
        self, *, name: str, scale_factor: Decimal, control_height_px: int, touch_target_px: int,
        spacing_unit_px: int,
    ) -> None:
        self._validate(
            name=name, scale_factor=scale_factor, control_height_px=control_height_px,
            touch_target_px=touch_target_px, spacing_unit_px=spacing_unit_px,
        )
        self.name = name.strip()
        self.scale_factor = scale_factor
        self.control_height_px = control_height_px
        self.touch_target_px = touch_target_px
        self.spacing_unit_px = spacing_unit_px
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()
