"""DesignToken — SET-22 "Tokens": one persisted, admin-editable design
token (spacing/typography/color/etc.). Generalizes the newer
`frontend/desktop/themes/tokens.py` module (Spacing, Typography, Radii,
Borders, Elevation, ControlHeights, IconSizes, TableMetrics, TouchTarget,
DialogMetrics — real values, but hardcoded Python constants with no DB
persistence and no way to override per-theme) into typed, persisted rows.

`theme_id=None` marks a GLOBAL token — applies to every theme unless a
theme-specific row with the same `token_key` overrides it (see
`policies/token_resolution_policy.py::resolve_tokens_for_theme`). Most
tokens (spacing, typography scale, control heights) are theme-independent
in the legacy module and stay global; `theme_id`-scoped rows exist for
values that genuinely differ per theme, chiefly COLOR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.appearance.enums import TokenCategory
from backend.domain.appearance.exceptions import AppearanceInvalidValueError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DesignToken:
    id: str
    theme_id: str | None
    token_key: str
    category: TokenCategory
    token_value: str
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, theme_id: str | None, token_key: str, category: TokenCategory, token_value: str,
    ) -> "DesignToken":
        if not token_key.strip():
            raise AppearanceInvalidValueError("token_key es obligatorio")
        if not token_value.strip():
            raise AppearanceInvalidValueError("token_value es obligatorio")
        return cls(
            id=new_uuid(), theme_id=validate_uuidv7(theme_id) if theme_id is not None else None,
            token_key=token_key.strip(), category=category, token_value=token_value.strip(),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def update_value(self, new_value: str) -> None:
        if not new_value.strip():
            raise AppearanceInvalidValueError("token_value es obligatorio")
        self.token_value = new_value.strip()
        self._touch()
