"""SET-3 — Configuration Governance infrastructure repositories against a
real (in-memory) SQLite born-clean schema: round-trip fidelity for every
`ValueType`, idempotent writes, version/scope uniqueness, and resolution
through repository-fetched entities end to end.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from backend.domain.settings.entities.configuration_definition import ConfigurationDefinition
from backend.domain.settings.entities.configuration_value import ConfigurationValue
from backend.domain.settings.enums import ScopeType, ValueType
from backend.domain.settings.exceptions import ConfigurationDefinitionNotFoundError
from backend.domain.settings.services.configuration_resolution_service import (
    ConfigurationResolutionService,
    ScopeContext,
)
from backend.domain.settings.value_objects.configuration_scope import ConfigurationScope
from backend.domain.settings.value_objects.effective_period import EffectivePeriod
from backend.infrastructure.db.repositories.settings.configuration_definition_repository import (
    SqliteConfigurationDefinitionRepository,
)
from backend.infrastructure.db.repositories.settings.configuration_value_repository import (
    SqliteConfigurationValueRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

_NOW = datetime.now(timezone.utc)


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def repos(conn):
    return SqliteConfigurationDefinitionRepository(conn), SqliteConfigurationValueRepository(conn)


def _definition(**overrides) -> ConfigurationDefinition:
    kwargs = dict(
        key="orders.weight_adjustment_tolerance_pct", module="orders",
        label="Tolerancia de peso", value_type=ValueType.PERCENT,
        allowed_scopes={ScopeType.GLOBAL, ScopeType.BRANCH, ScopeType.WORKSTATION},
        default_value=Decimal("5.00"),
    )
    kwargs.update(overrides)
    return ConfigurationDefinition.create(**kwargs)


class TestConfigurationDefinitionRepository:
    def test_round_trips_all_fields(self, conn, repos):
        def_repo, _ = repos
        definition = _definition(
            section="tolerancias", description="Tolerancia de ajuste de peso en recepción",
            validation_schema={"min": 0, "max": 100}, approval_required=True, sensitive=False,
            restart_required=True, offline_available=False, default_scope=ScopeType.BRANCH,
        )
        def_repo.save(definition)
        conn.commit()

        fetched = def_repo.get(definition.id)
        assert fetched.id == definition.id
        assert str(fetched.key) == str(definition.key)
        assert fetched.module == "orders"
        assert fetched.section == "tolerancias"
        assert fetched.value_type is ValueType.PERCENT
        assert fetched.default_value == Decimal("5.00")
        assert fetched.validation_schema == {"min": 0, "max": 100}
        assert fetched.allowed_scopes == frozenset({ScopeType.GLOBAL, ScopeType.BRANCH, ScopeType.WORKSTATION})
        assert fetched.default_scope is ScopeType.BRANCH
        assert fetched.approval_required is True
        assert fetched.restart_required is True
        assert fetched.offline_available is False

    def test_get_by_key(self, conn, repos):
        def_repo, _ = repos
        definition = _definition()
        def_repo.save(definition)
        conn.commit()
        assert def_repo.get_by_key(str(definition.key)).id == definition.id
        assert def_repo.get_by_key("does.not_exist") is None

    def test_key_uniqueness_enforced_by_schema(self, conn, repos):
        def_repo, _ = repos
        def_repo.save(_definition())
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            def_repo.save(_definition())
            conn.commit()
        conn.rollback()

    def test_list_by_module(self, conn, repos):
        def_repo, _ = repos
        def_repo.save(_definition(key="orders.a", module="orders"))
        def_repo.save(_definition(key="orders.b", module="orders"))
        def_repo.save(_definition(key="printing.c", module="printing", default_value=None))
        conn.commit()
        orders_defs = def_repo.list_by_module("orders")
        assert {str(d.key) for d in orders_defs} == {"orders.a", "orders.b"}

    def test_enum_definition_with_allowed_values_round_trips(self, conn, repos):
        def_repo, _ = repos
        definition = _definition(
            key="tickets.paper_size", value_type=ValueType.ENUM,
            allowed_values=("58MM", "80MM"), default_value="80MM",
            allowed_scopes={ScopeType.GLOBAL},
        )
        def_repo.save(definition)
        conn.commit()
        fetched = def_repo.get(definition.id)
        assert fetched.allowed_values == ("58MM", "80MM")
        assert fetched.default_value == "80MM"

    def test_definition_without_default_value_round_trips_none(self, conn, repos):
        def_repo, _ = repos
        definition = _definition(default_value=None)
        def_repo.save(definition)
        conn.commit()
        assert def_repo.get(definition.id).default_value is None


class TestConfigurationValueRepositoryRoundTrip:
    """One case per ValueType — value_json must survive the exact Python
    shape validate_type_shape() requires (Decimal never float, tz-aware
    datetime, etc.)."""

    @pytest.mark.parametrize("value_type, value", [
        (ValueType.BOOLEAN, True),
        (ValueType.STRING, "hola mundo"),
        (ValueType.INTEGER, 42),
        (ValueType.DECIMAL, Decimal("123.456")),
        (ValueType.MONEY, Decimal("1999.99")),
        (ValueType.PERCENT, Decimal("7.50")),
        (ValueType.DATE, date(2026, 12, 31)),
        (ValueType.TIME, time(8, 30)),
        (ValueType.DATETIME, _NOW),
        (ValueType.DURATION, timedelta(hours=2, minutes=30)),
        (ValueType.ENUM, "80MM"),
        (ValueType.MULTI_ENUM, ("a", "b", "c")),
        (ValueType.JSON_SCHEMA, {"type": "object", "properties": {"x": 1}}),
        (ValueType.UUID_REFERENCE, "01a02572-0000-7000-8000-000000000001"),
        (ValueType.SECRET_REFERENCE, "smtp_password"),
        (ValueType.FILE_REFERENCE, "asset-ref-001"),
        (ValueType.COLOR_TOKEN, "brand.primary"),
        (ValueType.TEMPLATE_REFERENCE, "template-ref-001"),
        (ValueType.DEVICE_REFERENCE, "device-ref-001"),
    ])
    def test_value_round_trips_exact_python_shape(self, conn, repos, value_type, value):
        def_repo, val_repo = repos
        allowed_values = ("a", "b", "c", "80MM", "58MM") if value_type in (
            ValueType.ENUM, ValueType.MULTI_ENUM,
        ) else None
        definition = _definition(
            key=f"roundtrip.{value_type.value.lower()}", value_type=value_type,
            default_value=None, allowed_values=allowed_values,
            allowed_scopes={ScopeType.GLOBAL},
        )
        def_repo.save(definition)
        conn.commit()

        configuration_value = ConfigurationValue.create(
            definition_id=definition.id, scope=ConfigurationScope.global_scope(), value=value,
            effective_period=EffectivePeriod.create(_NOW - timedelta(days=1)),
            created_by_user_id="u1",
        )
        val_repo.save(configuration_value)
        conn.commit()

        fetched = val_repo.get(configuration_value.id)
        assert fetched.value == value


class TestConfigurationValueRepositoryBehavior:
    def _saved_definition(self, def_repo, conn, **overrides):
        definition = _definition(**overrides)
        def_repo.save(definition)
        conn.commit()
        return definition

    def test_save_unknown_definition_raises(self, conn, repos):
        _, val_repo = repos
        orphan_value = ConfigurationValue.create(
            definition_id=new_uuid(), scope=ConfigurationScope.global_scope(), value=Decimal("1.0"),
            effective_period=EffectivePeriod.create(_NOW),
        )
        with pytest.raises(ConfigurationDefinitionNotFoundError):
            val_repo.save(orphan_value)

    def test_operation_id_uniqueness_enforced(self, conn, repos):
        def_repo, val_repo = repos
        definition = self._saved_definition(def_repo, conn)
        scope = ConfigurationScope.create(ScopeType.BRANCH, new_uuid())
        op_id = new_uuid()
        first = ConfigurationValue.create(
            definition_id=definition.id, scope=scope, value=Decimal("1.0"),
            effective_period=EffectivePeriod.create(_NOW),
        )
        val_repo.save(first, operation_id=op_id)
        conn.commit()

        second = ConfigurationValue.create(
            definition_id=definition.id, scope=scope, value=Decimal("2.0"),
            effective_period=EffectivePeriod.create(_NOW + timedelta(days=1)),
        )
        with pytest.raises(sqlite3.IntegrityError):
            val_repo.save(second, operation_id=op_id)
        conn.rollback()

    def test_version_uniqueness_per_definition_and_scope(self, conn, repos):
        def_repo, val_repo = repos
        definition = self._saved_definition(def_repo, conn)
        scope = ConfigurationScope.create(ScopeType.BRANCH, new_uuid())
        first = ConfigurationValue.create(
            definition_id=definition.id, scope=scope, value=Decimal("1.0"),
            effective_period=EffectivePeriod.create(_NOW),
        )
        val_repo.save(first)
        conn.commit()

        colliding = ConfigurationValue.create(
            definition_id=definition.id, scope=scope, value=Decimal("2.0"),
            effective_period=EffectivePeriod.create(_NOW + timedelta(days=1)),
        )  # also version 1 for the same (definition, scope) — must collide
        with pytest.raises(sqlite3.IntegrityError):
            val_repo.save(colliding)
        conn.rollback()

    def test_same_version_number_allowed_across_different_scopes(self, conn, repos):
        def_repo, val_repo = repos
        definition = self._saved_definition(def_repo, conn)
        branch_value = ConfigurationValue.create(
            definition_id=definition.id, scope=ConfigurationScope.create(ScopeType.BRANCH, new_uuid()),
            value=Decimal("1.0"), effective_period=EffectivePeriod.create(_NOW),
        )
        global_value = ConfigurationValue.create(
            definition_id=definition.id, scope=ConfigurationScope.global_scope(),
            value=Decimal("2.0"), effective_period=EffectivePeriod.create(_NOW),
        )
        val_repo.save(branch_value)
        val_repo.save(global_value)
        conn.commit()  # both version 1, different scopes — must not collide
        assert val_repo.get(branch_value.id) is not None
        assert val_repo.get(global_value.id) is not None

    def test_create_next_version_persists_as_a_new_row(self, conn, repos):
        def_repo, val_repo = repos
        definition = self._saved_definition(def_repo, conn)
        scope = ConfigurationScope.create(ScopeType.BRANCH, new_uuid())
        first = ConfigurationValue.create(
            definition_id=definition.id, scope=scope, value=Decimal("1.0"),
            effective_period=EffectivePeriod.create(_NOW - timedelta(days=2)),
        )
        val_repo.save(first)
        conn.commit()

        second = first.create_next_version(
            value=Decimal("2.0"), effective_period=EffectivePeriod.create(_NOW),
            created_by_user_id="u9", reason="ajuste",
        )
        val_repo.save(second)
        conn.commit()

        candidates = val_repo.list_candidates(definition.id, (scope,))
        assert len(candidates) == 2
        assert {c.version.value for c in candidates} == {1, 2}
        fetched_second = val_repo.get(second.id)
        assert fetched_second.previous_version_id == first.id

    def test_list_active_for_scope(self, conn, repos):
        def_repo, val_repo = repos
        definition = self._saved_definition(def_repo, conn)
        branch_id = new_uuid()
        scope = ConfigurationScope.create(ScopeType.BRANCH, branch_id)
        active_value = ConfigurationValue.create(
            definition_id=definition.id, scope=scope, value=Decimal("1.0"),
            effective_period=EffectivePeriod.create(_NOW - timedelta(days=1)),
        )
        active_value.auto_approve("u1")
        active_value.activate("u1", at=_NOW)
        val_repo.save(active_value)
        conn.commit()

        draft_value = ConfigurationValue.create(
            definition_id=definition.id, scope=ConfigurationScope.global_scope(), value=Decimal("2.0"),
            effective_period=EffectivePeriod.create(_NOW),
        )
        val_repo.save(draft_value)
        conn.commit()

        results = val_repo.list_active_for_scope(scope)
        assert [r.id for r in results] == [active_value.id]


class TestResolutionAgainstRepositories:
    def test_end_to_end_inheritance_through_persisted_rows(self, conn, repos):
        def_repo, val_repo = repos
        definition = self._make_definition(def_repo, conn)
        branch_id, workstation_id = new_uuid(), new_uuid()

        global_value = self._active(val_repo, definition, ConfigurationScope.global_scope(), Decimal("1.0"))
        branch_value = self._active(
            val_repo, definition, ConfigurationScope.create(ScopeType.BRANCH, branch_id), Decimal("2.0"),
        )
        conn.commit()

        candidates = val_repo.list_candidates(
            definition.id,
            (
                ConfigurationScope.global_scope(),
                ConfigurationScope.create(ScopeType.BRANCH, branch_id),
                ConfigurationScope.create(ScopeType.WORKSTATION, workstation_id),
            ),
        )
        service = ConfigurationResolutionService()
        resolved = service.resolve(
            def_repo.get(definition.id), candidates,
            context=ScopeContext({ScopeType.BRANCH: branch_id, ScopeType.WORKSTATION: workstation_id}),
        )
        assert resolved.value == Decimal("2.0")
        assert resolved.source_scope.scope_type is ScopeType.BRANCH

    @staticmethod
    def _make_definition(def_repo, conn) -> ConfigurationDefinition:
        definition = _definition(key="printing.default_copies", default_value=Decimal("1.0"))
        def_repo.save(definition)
        conn.commit()
        return definition

    @staticmethod
    def _active(val_repo, definition, scope, value) -> ConfigurationValue:
        configuration_value = ConfigurationValue.create(
            definition_id=definition.id, scope=scope, value=value,
            effective_period=EffectivePeriod.create(_NOW - timedelta(days=1)),
            created_by_user_id="u1",
        )
        configuration_value.auto_approve("u2")
        configuration_value.activate("u2", at=_NOW)
        val_repo.save(configuration_value)
        return configuration_value
