"""SET-4 — ConfigurationCache (§55): keyed lookup, event-driven
invalidation (never a bare TTL), and composition with
ConfigurationResolutionService. Pure domain — no DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.domain.settings.entities.configuration_definition import ConfigurationDefinition
from backend.domain.settings.entities.configuration_value import ConfigurationValue
from backend.domain.settings.enums import ScopeType, ValueType
from backend.domain.settings.events import ConfigurationEvents
from backend.domain.settings.services.configuration_cache_service import (
    ConfigurationCache,
    ConfigurationCacheKey,
)
from backend.domain.settings.services.configuration_resolution_service import (
    ConfigurationResolutionService,
    ScopeContext,
)
from backend.domain.settings.value_objects.configuration_scope import ConfigurationScope
from backend.domain.settings.value_objects.effective_period import EffectivePeriod
from backend.shared.ids import new_uuid

_NOW = datetime.now(timezone.utc)


def _definition(**overrides) -> ConfigurationDefinition:
    kwargs = dict(
        key="printing.default_copies", module="printing", label="Copias por defecto",
        value_type=ValueType.INTEGER, allowed_scopes={ScopeType.GLOBAL, ScopeType.BRANCH},
        default_value=1,
    )
    kwargs.update(overrides)
    return ConfigurationDefinition.create(**kwargs)


def _active_value(definition, scope, value) -> ConfigurationValue:
    configuration_value = ConfigurationValue.create(
        definition_id=definition.id, scope=scope, value=value,
        effective_period=EffectivePeriod.create(_NOW - timedelta(days=1)),
        created_by_user_id="u1",
    )
    configuration_value.auto_approve("u2")
    configuration_value.activate("u2", at=_NOW)
    return configuration_value


class TestConfigurationCacheKey:
    def test_same_context_produces_equal_keys(self):
        branch_id = new_uuid()
        key_a = ConfigurationCacheKey.build("def-1", ScopeContext({ScopeType.BRANCH: branch_id}))
        key_b = ConfigurationCacheKey.build("def-1", ScopeContext({ScopeType.BRANCH: branch_id}))
        assert key_a == key_b
        assert hash(key_a) == hash(key_b)

    def test_key_is_independent_of_dict_insertion_order(self):
        branch_id, workstation_id = new_uuid(), new_uuid()
        context_a = ScopeContext({ScopeType.BRANCH: branch_id, ScopeType.WORKSTATION: workstation_id})
        context_b = ScopeContext({ScopeType.WORKSTATION: workstation_id, ScopeType.BRANCH: branch_id})
        assert ConfigurationCacheKey.build("def-1", context_a) == ConfigurationCacheKey.build("def-1", context_b)

    def test_different_definitions_or_scopes_produce_different_keys(self):
        branch_id = new_uuid()
        key_a = ConfigurationCacheKey.build("def-1", ScopeContext({ScopeType.BRANCH: branch_id}))
        key_b = ConfigurationCacheKey.build("def-2", ScopeContext({ScopeType.BRANCH: branch_id}))
        key_c = ConfigurationCacheKey.build("def-1", ScopeContext({ScopeType.BRANCH: new_uuid()}))
        assert key_a != key_b
        assert key_a != key_c


class TestConfigurationCacheBasics:
    def test_miss_returns_none(self):
        cache = ConfigurationCache()
        key = ConfigurationCacheKey.build("def-1", ScopeContext({}))
        assert cache.get(key) is None
        assert len(cache) == 0

    def test_put_then_get_hits(self):
        cache = ConfigurationCache()
        definition = _definition()
        service = ConfigurationResolutionService()
        resolved = service.resolve(definition, [], context=ScopeContext({}))
        key = ConfigurationCacheKey.build(definition.id, ScopeContext({}))
        cache.put(key, resolved)
        assert cache.get(key) is resolved
        assert len(cache) == 1

    def test_clear_empties_everything(self):
        cache = ConfigurationCache()
        key = ConfigurationCacheKey.build("def-1", ScopeContext({}))
        cache.put(key, object())
        cache.clear()
        assert len(cache) == 0

    def test_invalidate_definition_only_clears_that_definitions_entries(self):
        cache = ConfigurationCache()
        key_a1 = ConfigurationCacheKey.build("def-a", ScopeContext({ScopeType.BRANCH: new_uuid()}))
        key_a2 = ConfigurationCacheKey.build("def-a", ScopeContext({ScopeType.BRANCH: new_uuid()}))
        key_b = ConfigurationCacheKey.build("def-b", ScopeContext({}))
        cache.put(key_a1, object())
        cache.put(key_a2, object())
        cache.put(key_b, object())
        cache.invalidate_definition("def-a")
        assert cache.get(key_a1) is None
        assert cache.get(key_a2) is None
        assert cache.get(key_b) is not None
        assert len(cache) == 1


class TestConfigurationCacheEventInvalidation:
    @pytest.mark.parametrize("event_name", [
        ConfigurationEvents.ACTIVATED, ConfigurationEvents.SCHEDULED,
        ConfigurationEvents.EXPIRED, ConfigurationEvents.ROLLED_BACK,
    ])
    def test_lifecycle_events_invalidate_the_definition(self, event_name):
        cache = ConfigurationCache()
        key = ConfigurationCacheKey.build("def-a", ScopeContext({}))
        cache.put(key, object())
        cache.handle_event(event_name, definition_id="def-a")
        assert cache.get(key) is None

    def test_unrelated_event_does_not_invalidate(self):
        cache = ConfigurationCache()
        key = ConfigurationCacheKey.build("def-a", ScopeContext({}))
        cache.put(key, object())
        cache.handle_event(ConfigurationEvents.DEFINITION_CREATED, definition_id="def-a")
        assert cache.get(key) is not None

    def test_cache_invalidated_event_with_definition_id_clears_only_that_definition(self):
        cache = ConfigurationCache()
        key_a = ConfigurationCacheKey.build("def-a", ScopeContext({}))
        key_b = ConfigurationCacheKey.build("def-b", ScopeContext({}))
        cache.put(key_a, object())
        cache.put(key_b, object())
        cache.handle_event(ConfigurationEvents.CACHE_INVALIDATED, definition_id="def-a")
        assert cache.get(key_a) is None
        assert cache.get(key_b) is not None

    def test_cache_invalidated_event_without_definition_id_clears_everything(self):
        cache = ConfigurationCache()
        cache.put(ConfigurationCacheKey.build("def-a", ScopeContext({})), object())
        cache.put(ConfigurationCacheKey.build("def-b", ScopeContext({})), object())
        cache.handle_event(ConfigurationEvents.CACHE_INVALIDATED, definition_id=None)
        assert len(cache) == 0

    def test_event_for_a_definition_with_no_cached_entries_is_a_no_op(self):
        cache = ConfigurationCache()
        cache.handle_event(ConfigurationEvents.ACTIVATED, definition_id="never-cached")
        assert len(cache) == 0


class TestCacheResolutionComposition:
    """The shape a future application-layer QueryService follows: check
    cache, resolve on miss, cache the result, and go stale-free by
    invalidating on the events that could change the answer."""

    def test_cache_then_resolve_composition_round_trip(self):
        definition = _definition()
        branch_id = new_uuid()
        branch_value = _active_value(
            definition, ConfigurationScope.create(ScopeType.BRANCH, branch_id), 5,
        )
        candidates = [branch_value]
        context = ScopeContext({ScopeType.BRANCH: branch_id})
        cache = ConfigurationCache()
        service = ConfigurationResolutionService()
        key = ConfigurationCacheKey.build(definition.id, context)

        assert cache.get(key) is None  # miss
        resolved = service.resolve(definition, candidates, context=context)
        cache.put(key, resolved)

        cached = cache.get(key)  # hit — no need to re-walk candidates
        assert cached.value == 5
        assert cached is resolved

    def test_invalidation_forces_a_fresh_resolve_after_rollback(self):
        definition = _definition()
        branch_id = new_uuid()
        branch_value = _active_value(
            definition, ConfigurationScope.create(ScopeType.BRANCH, branch_id), 5,
        )
        context = ScopeContext({ScopeType.BRANCH: branch_id})
        cache = ConfigurationCache()
        service = ConfigurationResolutionService()
        key = ConfigurationCacheKey.build(definition.id, context)

        cache.put(key, service.resolve(definition, [branch_value], context=context))
        assert cache.get(key).value == 5

        # The value gets rolled back — the cache must not keep serving 5.
        branch_value.mark_rolled_back()
        cache.handle_event(ConfigurationEvents.ROLLED_BACK, definition_id=definition.id)
        assert cache.get(key) is None

        rolled_back_candidates: list[ConfigurationValue] = []  # no ACTIVE candidate left
        fresh = service.resolve(definition, rolled_back_candidates, context=context)
        cache.put(key, fresh)
        assert cache.get(key).value == 1  # falls back to definition default
