"""SetDefaultThemeUseCase — "Apariencia" section, UI/UX phase. Thin
orchestration over `backend/domain/appearance/` (SET-22): unmark the
current default *first*, so the switch itself never trips
`theme_default_policy.assert_can_set_default`'s own "at most one active
default" guard — that guard exists to catch a caller trying to create a
SECOND default alongside an existing one, not to block a legitimate
switch. Re-checked immediately before marking the new default (against
the now-updated repository state) so the invariant is still verified,
not just assumed — the schema's `ux_themes_single_default` partial
unique index is the final backstop either way (defense in depth, as
documented in SET-22).
"""

from __future__ import annotations

from backend.domain.appearance.entities.theme import Theme
from backend.domain.appearance.exceptions import ThemeNotFoundError
from backend.domain.appearance.policies.theme_default_policy import assert_can_set_default
from backend.infrastructure.db.repositories.appearance.theme_repository import SqliteThemeRepository


class SetDefaultThemeUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._themes = SqliteThemeRepository(connection)

    def execute(self, *, theme_id: str) -> Theme:
        theme = self._themes.get(theme_id)
        if theme is None:
            raise ThemeNotFoundError(f"Tema {theme_id} no encontrado")

        current_default = self._themes.get_default()
        if current_default is not None and current_default.id != theme.id:
            current_default.unmark_default()
            self._themes.save(current_default)

        assert_can_set_default(self._themes.list_active(), theme)
        theme.mark_default()
        self._themes.save(theme)
        self._conn.commit()
        return theme
