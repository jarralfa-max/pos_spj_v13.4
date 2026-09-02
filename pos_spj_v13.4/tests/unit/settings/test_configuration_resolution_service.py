"""SET-2/SET-4 — ConfigurationResolutionService: inheritance walk (§7).
Pure domain — no DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.domain.settings.entities.configuration_definition import ConfigurationDefinition
from backend.domain.settings.entities.configuration_value import ConfigurationValue
from backend.domain.settings.enums import ScopeType, ValueType
from backend.domain.settings.exceptions import ConfigurationValueNotFoundError
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
        key="printing.default_printer_id", module="printing", label="Impresora predeterminada",
        value_type=ValueType.PERCENT, allowed_scopes={
            ScopeType.GLOBAL, ScopeType.COMPANY, ScopeType.BRANCH, ScopeType.WORKSTATION,
        },
        default_value=Decimal("5.00"),
    )
    kwargs.update(overrides)
    return ConfigurationDefinition.create(**kwargs)


def _active_value(definition, scope: ConfigurationScope, value=Decimal("1.0")) -> ConfigurationValue:
    configuration_value = ConfigurationValue.create(
        definition_id=definition.id, scope=scope, value=value,
        effective_period=EffectivePeriod.create(_NOW - timedelta(days=1)),
        created_by_user_id="u1",
    )
    configuration_value.auto_approve("u2")
    configuration_value.activate("u2", at=_NOW)
    return configuration_value


class TestResolution:
    def test_falls_back_to_definition_default_when_no_candidates(self):
        definition = _definition()
        service = ConfigurationResolutionService()
        resolved = service.resolve(definition, [], context=ScopeContext({}))
        assert resolved.value == Decimal("5.00")
        assert resolved.source_scope is None
        assert resolved.configuration_value is None

    def test_raises_when_no_candidates_and_no_default(self):
        definition = _definition(default_value=None)
        service = ConfigurationResolutionService()
        with pytest.raises(ConfigurationValueNotFoundError):
            service.resolve(definition, [], context=ScopeContext({}))

    def test_global_value_used_when_no_more_specific_scope_present(self):
        definition = _definition()
        global_value = _active_value(definition, ConfigurationScope.global_scope(), Decimal("2.0"))
        service = ConfigurationResolutionService()
        resolved = service.resolve(definition, [global_value], context=ScopeContext({}))
        assert resolved.value == Decimal("2.0")
        assert resolved.source_scope.scope_type is ScopeType.GLOBAL

    def test_most_specific_scope_wins_over_global(self):
        definition = _definition()
        company_id, branch_id, workstation_id = new_uuid(), new_uuid(), new_uuid()
        global_value = _active_value(definition, ConfigurationScope.global_scope(), Decimal("1.0"))
        company_value = _active_value(
            definition, ConfigurationScope.create(ScopeType.COMPANY, company_id), Decimal("2.0"),
        )
        branch_value = _active_value(
            definition, ConfigurationScope.create(ScopeType.BRANCH, branch_id), Decimal("3.0"),
        )
        workstation_value = _active_value(
            definition, ConfigurationScope.create(ScopeType.WORKSTATION, workstation_id), Decimal("4.0"),
        )
        service = ConfigurationResolutionService()
        context = ScopeContext({
            ScopeType.COMPANY: company_id, ScopeType.BRANCH: branch_id,
            ScopeType.WORKSTATION: workstation_id,
        })
        resolved = service.resolve(
            definition, [global_value, company_value, branch_value, workstation_value], context=context,
        )
        assert resolved.value == Decimal("4.0")
        assert resolved.source_scope.scope_type is ScopeType.WORKSTATION

    def test_falls_back_to_branch_when_workstation_has_no_value(self):
        definition = _definition()
        branch_id, workstation_id = new_uuid(), new_uuid()
        branch_value = _active_value(
            definition, ConfigurationScope.create(ScopeType.BRANCH, branch_id), Decimal("3.0"),
        )
        service = ConfigurationResolutionService()
        context = ScopeContext({ScopeType.BRANCH: branch_id, ScopeType.WORKSTATION: workstation_id})
        resolved = service.resolve(definition, [branch_value], context=context)
        assert resolved.value == Decimal("3.0")
        assert resolved.source_scope.scope_type is ScopeType.BRANCH

    def test_expired_candidate_is_not_used(self):
        definition = _definition()
        branch_id = new_uuid()
        branch_value = ConfigurationValue.create(
            definition_id=definition.id, scope=ConfigurationScope.create(ScopeType.BRANCH, branch_id),
            value=Decimal("3.0"),
            effective_period=EffectivePeriod.create(_NOW - timedelta(days=10), _NOW - timedelta(days=5)),
            created_by_user_id="u1",
        )
        branch_value.auto_approve("u2")
        branch_value.activate("u2", at=_NOW - timedelta(days=9))
        branch_value.expire(at=_NOW - timedelta(hours=1))
        service = ConfigurationResolutionService()
        context = ScopeContext({ScopeType.BRANCH: branch_id})
        resolved = service.resolve(definition, [branch_value], context=context, at=_NOW)
        assert resolved.value == Decimal("5.00")  # falls back to default
        assert resolved.source_scope is None

    def test_only_matches_own_definition_id(self):
        definition_a = _definition(key="printing.a")
        definition_b = _definition(key="printing.b", default_value=Decimal("9.0"))
        branch_id = new_uuid()
        value_for_a = _active_value(
            definition_a, ConfigurationScope.create(ScopeType.BRANCH, branch_id), Decimal("1.0"),
        )
        service = ConfigurationResolutionService()
        context = ScopeContext({ScopeType.BRANCH: branch_id})
        resolved = service.resolve(definition_b, [value_for_a], context=context)
        assert resolved.value == Decimal("9.0")  # definition_b's default, unaffected by A's value

    def test_scope_present_in_context_but_not_in_allowed_scopes_is_ignored(self):
        # WORKSTATION isn't in this definition's allowed_scopes at all — a
        # value there (however it got created) must never be considered,
        # not even as a fallback candidate.
        definition = _definition(allowed_scopes={ScopeType.GLOBAL, ScopeType.BRANCH})
        branch_id, workstation_id = new_uuid(), new_uuid()
        global_value = _active_value(definition, ConfigurationScope.global_scope(), Decimal("1.0"))
        service = ConfigurationResolutionService()
        context = ScopeContext({ScopeType.BRANCH: branch_id, ScopeType.WORKSTATION: workstation_id})
        resolved = service.resolve(definition, [global_value], context=context)
        assert resolved.value == Decimal("1.0")
        assert resolved.source_scope.scope_type is ScopeType.GLOBAL

    def test_tie_break_picks_the_most_recently_started_period(self):
        # Two ACTIVE candidates at the identical scope should not happen in
        # practice (the version-uniqueness index enforces one lineage per
        # scope), but the resolver defends against it defensively by
        # picking the one with the latest effective_from.
        definition = _definition()
        branch_id = new_uuid()
        scope = ConfigurationScope.create(ScopeType.BRANCH, branch_id)
        older = ConfigurationValue.create(
            definition_id=definition.id, scope=scope, value=Decimal("1.0"),
            effective_period=EffectivePeriod.create(_NOW - timedelta(days=10)),
        )
        older.auto_approve("u1")
        older.activate("u1", at=_NOW - timedelta(days=10))
        newer = ConfigurationValue.create(
            definition_id=definition.id, scope=scope, value=Decimal("2.0"),
            effective_period=EffectivePeriod.create(_NOW - timedelta(days=1)),
        )
        newer.auto_approve("u1")
        newer.activate("u1", at=_NOW - timedelta(days=1))
        service = ConfigurationResolutionService()
        resolved = service.resolve(
            definition, [older, newer], context=ScopeContext({ScopeType.BRANCH: branch_id}),
        )
        assert resolved.value == Decimal("2.0")

    def test_inheritance_disabled_ignores_more_specific_scopes_end_to_end(self):
        definition = _definition(inheritance_enabled=False, default_scope=ScopeType.BRANCH)
        branch_id, workstation_id = new_uuid(), new_uuid()
        # A WORKSTATION value exists and is ACTIVE, but with inheritance
        # disabled only default_scope (BRANCH) may ever resolve.
        workstation_value = _active_value(
            definition, ConfigurationScope.create(ScopeType.WORKSTATION, workstation_id), Decimal("99.0"),
        )
        branch_value = _active_value(
            definition, ConfigurationScope.create(ScopeType.BRANCH, branch_id), Decimal("3.0"),
        )
        service = ConfigurationResolutionService()
        context = ScopeContext({ScopeType.BRANCH: branch_id, ScopeType.WORKSTATION: workstation_id})
        resolved = service.resolve(definition, [workstation_value, branch_value], context=context)
        assert resolved.value == Decimal("3.0")
        assert resolved.source_scope.scope_type is ScopeType.BRANCH
