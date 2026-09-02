"""ConfigurationResolutionService — walks the inheritance chain to find
the effective value of a definition for a concrete operation (§7).

Pure domain logic: takes an already-fetched list of `ConfigurationValue`
candidates (the repository/QueryService's job, in a later SET) and a
`ScopeContext` describing which concrete scope ids apply right now (e.g.
"this workstation, in this branch, in this company"). The UI never
resolves inheritance itself (§7: "La UI no resuelve herencias.").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.settings.entities.configuration_value import ConfigurationValue
from backend.domain.settings.enums import ScopeType
from backend.domain.settings.exceptions import ConfigurationValueNotFoundError
from backend.domain.settings.policies.configuration_inheritance_policy import resolution_order
from backend.domain.settings.value_objects.configuration_scope import ConfigurationScope


@dataclass(frozen=True, slots=True)
class ScopeContext:
    """Concrete scope ids applicable to the current operation, e.g.
    ``{ScopeType.WORKSTATION: "...", ScopeType.BRANCH: "...", ScopeType.COMPANY: "..."}``.
    Scopes the caller has no id for are simply skipped during resolution."""

    scope_ids: dict[ScopeType, str] = field(default_factory=dict)

    def id_for(self, scope_type: ScopeType) -> str | None:
        return self.scope_ids.get(scope_type)


@dataclass(frozen=True, slots=True)
class ResolvedConfiguration:
    value: object
    source_scope: ConfigurationScope | None  # None means the definition's default_value was used
    configuration_value: ConfigurationValue | None  # None when it fell back to the default


class ConfigurationResolutionService:
    def resolve(
        self, definition, candidates: list[ConfigurationValue], *,
        context: ScopeContext, at: datetime | None = None,
    ) -> ResolvedConfiguration:
        moment = at or datetime.now(timezone.utc)
        own_candidates = [c for c in candidates if c.definition_id == definition.id]

        for scope_type in resolution_order(definition):
            if scope_type is ScopeType.GLOBAL:
                target_scope = ConfigurationScope.global_scope()
            else:
                scope_id = context.id_for(scope_type)
                if scope_id is None:
                    continue
                target_scope = ConfigurationScope.create(scope_type, scope_id)

            matches = [
                candidate for candidate in own_candidates
                if candidate.scope.matches(target_scope) and candidate.is_effective(moment)
            ]
            if matches:
                # One ACTIVE value per (definition, scope) is expected; break
                # ties defensively by the most recently started period.
                chosen = max(matches, key=lambda candidate: candidate.effective_period.effective_from)
                return ResolvedConfiguration(value=chosen.value, source_scope=target_scope, configuration_value=chosen)

        if definition.default_value is not None:
            return ResolvedConfiguration(value=definition.default_value, source_scope=None, configuration_value=None)

        raise ConfigurationValueNotFoundError(
            f"{definition.key}: no hay valor activo en ningún ámbito aplicable y la "
            "definición no tiene default_value."
        )
