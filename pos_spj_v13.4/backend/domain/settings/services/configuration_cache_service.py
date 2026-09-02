"""ConfigurationCache — §55: "No permitir cachés eternas sin versión."

Caches `ResolvedConfiguration` results keyed by (definition, concrete
scope context) so repeated resolution doesn't re-walk the inheritance
chain on every read. Never eternal: every entry is invalidated by the
domain event that could make it stale, not by a time-based TTL — a config
change is either reflected immediately (event fires) or not at all
(nothing stays silently wrong past its freshness window).

Composition, not inheritance: this does not wrap or replace
`ConfigurationResolutionService`, which stays pure/stateless. A caller
(the future application-layer QueryService) checks the cache first, calls
the resolution service on a miss, then stores the result here — see
`tests/unit/settings/test_configuration_cache_service.py` for the
composition shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.settings.events import ConfigurationEvents
from backend.domain.settings.services.configuration_resolution_service import (
    ResolvedConfiguration,
    ScopeContext,
)

# Events that can change a definition's effective value anywhere in its
# scope tree — any of these invalidates every cached entry for that
# definition_id, not just the one scope that changed (a BRANCH activation
# can change what a WORKSTATION under it resolves to via fallback).
_INVALIDATING_EVENTS = frozenset({
    ConfigurationEvents.ACTIVATED,
    ConfigurationEvents.SCHEDULED,
    ConfigurationEvents.EXPIRED,
    ConfigurationEvents.ROLLED_BACK,
})


@dataclass(frozen=True, slots=True)
class ConfigurationCacheKey:
    definition_id: str
    scope_signature: tuple[tuple[str, str], ...]

    @classmethod
    def build(cls, definition_id: str, context: ScopeContext) -> "ConfigurationCacheKey":
        signature = tuple(sorted(
            (scope_type.value, scope_id) for scope_type, scope_id in context.scope_ids.items()
        ))
        return cls(definition_id, signature)


class ConfigurationCache:
    def __init__(self) -> None:
        self._entries: dict[ConfigurationCacheKey, ResolvedConfiguration] = {}

    def get(self, key: ConfigurationCacheKey) -> ResolvedConfiguration | None:
        return self._entries.get(key)

    def put(self, key: ConfigurationCacheKey, resolved: ResolvedConfiguration) -> None:
        self._entries[key] = resolved

    def invalidate_definition(self, definition_id: str) -> None:
        for key in [k for k in self._entries if k.definition_id == definition_id]:
            del self._entries[key]

    def clear(self) -> None:
        self._entries.clear()

    def handle_event(self, event_name: str, *, definition_id: str | None) -> None:
        """Wire this to the EventBus (application layer, a later SET) so a
        publish of any invalidating event evicts affected entries without
        the cache ever needing to know *why* — only that something changed."""
        if event_name == ConfigurationEvents.CACHE_INVALIDATED:
            if definition_id is None:
                self.clear()
            else:
                self.invalidate_definition(definition_id)
            return
        if event_name in _INVALIDATING_EVENTS and definition_id is not None:
            self.invalidate_definition(definition_id)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._entries)
