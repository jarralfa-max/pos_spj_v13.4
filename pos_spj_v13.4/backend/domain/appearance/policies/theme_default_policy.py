"""ThemeDefaultPolicy — SET-22 "Themes": at most one active `Theme` may
be `is_default` at a time. Enforced here at the domain layer *and* again
at the schema layer (`ux_themes_single_default`, a partial unique index)
— defense in depth, same double-enforcement pattern the segregation-of-
duties check uses (`feature_flag_approval_policy`/
`configuration_approval_policy`, checked in-process before the DB would
ever reject it).
"""

from __future__ import annotations

from backend.domain.appearance.entities.theme import Theme
from backend.domain.appearance.exceptions import DuplicateDefaultThemeError


def assert_can_set_default(existing_themes: list[Theme], candidate: Theme) -> None:
    for theme in existing_themes:
        if theme.id == candidate.id:
            continue
        if theme.active and theme.is_default:
            raise DuplicateDefaultThemeError(
                f"El tema '{theme.code}' ya es el default activo; desmárquelo antes de asignar otro."
            )
