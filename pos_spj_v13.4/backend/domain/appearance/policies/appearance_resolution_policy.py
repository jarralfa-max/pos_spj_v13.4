"""AppearanceResolutionPolicy — SET-22 "Light/dark" + "Density": which
theme+density a session should actually use, generalizing
`core/services/theme_service.py::get_user_preferences()` (which only
ever reads one flat global pair, no scoping).

Resolution order: the most specific *matching* active preference wins
(USER > BRANCH > GLOBAL — `enums.SCOPE_SPECIFICITY_ORDER`), the same
"most specific match wins" principle already established independently by
`backend.domain.settings.services.configuration_resolution_service`,
`backend.domain.device_management.policies.print_routing_policy`, and
`backend.domain.feature_flags.policies.feature_flag_evaluation_policy`
(bounded-context independence — reimplemented here, not imported). No
matching preference falls back to the caller-supplied
`default_theme_id`/`default_density` — mirroring the legacy service's own
hardcoded `{'theme': 'Oscuro', 'density': 'Normal'}` fallback, just now an
explicit parameter instead of a buried literal.
"""

from __future__ import annotations

from backend.domain.appearance.entities.appearance_preference import AppearancePreference
from backend.domain.appearance.enums import SCOPE_SPECIFICITY_ORDER, AppearanceScopeType, DensityLevel


def resolve_appearance(
    preferences: list[AppearancePreference], *, branch_id: str | None = None, user_id: str | None = None,
    default_theme_id: str, default_density: DensityLevel = DensityLevel.NORMAL,
) -> tuple[str, DensityLevel]:
    candidates_by_scope = {
        AppearanceScopeType.USER: user_id, AppearanceScopeType.BRANCH: branch_id,
        AppearanceScopeType.GLOBAL: None,
    }
    for scope_type in SCOPE_SPECIFICITY_ORDER:
        scope_id = candidates_by_scope[scope_type]
        if scope_type is not AppearanceScopeType.GLOBAL and scope_id is None:
            continue
        for preference in preferences:
            if not preference.matches(scope_type, scope_id):
                continue
            return preference.theme_id, preference.density_level

    return default_theme_id, default_density
