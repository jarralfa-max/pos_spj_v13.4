"""SET-2 — Settings value objects: ConfigurationKey, ConfigurationScope,
EffectivePeriod, VersionNumber, typed value-shape validation. Pure domain
— no DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.domain.settings.enums import ScopeType, ValueType
from backend.domain.settings.exceptions import (
    ConfigurationInvalidValueError,
    ConfigurationScopeNotAllowedError,
)
from backend.domain.settings.value_objects.authorization_grant import AuthorizationGrant
from backend.domain.settings.value_objects.configuration_key import ConfigurationKey
from backend.domain.settings.value_objects.configuration_scope import ConfigurationScope
from backend.domain.settings.value_objects.configuration_value_object import validate_type_shape
from backend.domain.settings.value_objects.effective_period import EffectivePeriod
from backend.domain.settings.value_objects.version_number import VersionNumber
from backend.shared.ids import new_uuid

_NOW = datetime.now(timezone.utc)


class TestConfigurationKey:
    def test_accepts_dotted_snake_case(self):
        key = ConfigurationKey.create("orders.weight_adjustment_tolerance_pct")
        assert key.value == "orders.weight_adjustment_tolerance_pct"
        assert key.module == "orders"

    @pytest.mark.parametrize("raw", ["novalidsegment", "Orders.Tolerance", "orders.", ".tolerance", "orders..x", "orders.1x"])
    def test_rejects_invalid_shapes(self, raw):
        with pytest.raises(ConfigurationInvalidValueError):
            ConfigurationKey.create(raw)


class TestConfigurationScope:
    def test_global_scope_has_no_id(self):
        scope = ConfigurationScope.global_scope()
        assert scope.scope_type is ScopeType.GLOBAL
        assert scope.scope_id is None

    def test_global_scope_rejects_explicit_id(self):
        with pytest.raises(ConfigurationScopeNotAllowedError):
            ConfigurationScope.create(ScopeType.GLOBAL, new_uuid())

    def test_branch_scope_requires_uuidv7(self):
        with pytest.raises(ValueError):
            ConfigurationScope.create(ScopeType.BRANCH, "1")

    def test_branch_scope_accepts_uuidv7(self):
        branch_id = new_uuid()
        scope = ConfigurationScope.create(ScopeType.BRANCH, branch_id)
        assert scope.scope_id == branch_id

    def test_non_global_scope_requires_id(self):
        with pytest.raises(ConfigurationScopeNotAllowedError):
            ConfigurationScope.create(ScopeType.BRANCH, None)

    def test_code_based_scope_accepts_logical_code(self):
        scope = ConfigurationScope.create(ScopeType.MODULE, "ventas")
        assert scope.scope_id == "ventas"

    def test_matches(self):
        branch_id = new_uuid()
        a = ConfigurationScope.create(ScopeType.BRANCH, branch_id)
        b = ConfigurationScope.create(ScopeType.BRANCH, branch_id)
        c = ConfigurationScope.create(ScopeType.BRANCH, new_uuid())
        assert a.matches(b)
        assert not a.matches(c)


class TestEffectivePeriod:
    def test_requires_timezone_aware_from(self):
        with pytest.raises(ConfigurationInvalidValueError):
            EffectivePeriod.create(datetime(2026, 1, 1))

    def test_effective_to_must_be_after_effective_from(self):
        with pytest.raises(ConfigurationInvalidValueError):
            EffectivePeriod.create(_NOW, _NOW - timedelta(days=1))

    def test_contains_open_ended(self):
        period = EffectivePeriod.create(_NOW - timedelta(days=1))
        assert period.contains(_NOW)
        assert not period.contains(_NOW - timedelta(days=2))

    def test_contains_bounded(self):
        period = EffectivePeriod.create(_NOW - timedelta(days=1), _NOW + timedelta(days=1))
        assert period.contains(_NOW)
        assert not period.contains(_NOW + timedelta(days=2))

    def test_has_expired(self):
        period = EffectivePeriod.create(_NOW - timedelta(days=2), _NOW - timedelta(days=1))
        assert period.has_expired(_NOW)

    def test_is_future(self):
        period = EffectivePeriod.create(_NOW + timedelta(days=1))
        assert period.is_future(_NOW)
        assert not period.is_future(_NOW + timedelta(days=2))


class TestVersionNumber:
    def test_first_is_one(self):
        assert VersionNumber.first().value == 1

    def test_next_increments(self):
        assert VersionNumber.first().next().value == 2

    def test_rejects_zero_and_negative(self):
        with pytest.raises(ConfigurationInvalidValueError):
            VersionNumber(0)
        with pytest.raises(ConfigurationInvalidValueError):
            VersionNumber(-1)

    def test_rejects_bool(self):
        with pytest.raises(ConfigurationInvalidValueError):
            VersionNumber(True)


class TestValidateTypeShape:
    def test_boolean(self):
        validate_type_shape(ValueType.BOOLEAN, True)
        with pytest.raises(ConfigurationInvalidValueError):
            validate_type_shape(ValueType.BOOLEAN, 1)

    def test_integer_rejects_bool(self):
        with pytest.raises(ConfigurationInvalidValueError):
            validate_type_shape(ValueType.INTEGER, True)

    def test_decimal_rejects_float(self):
        with pytest.raises(ConfigurationInvalidValueError):
            validate_type_shape(ValueType.DECIMAL, 5.0)
        validate_type_shape(ValueType.DECIMAL, Decimal("5.0"))

    def test_money_and_percent_require_decimal(self):
        validate_type_shape(ValueType.MONEY, Decimal("10.00"))
        validate_type_shape(ValueType.PERCENT, Decimal("5.00"))
        with pytest.raises(ConfigurationInvalidValueError):
            validate_type_shape(ValueType.PERCENT, "5")

    def test_datetime_requires_tz(self):
        with pytest.raises(ConfigurationInvalidValueError):
            validate_type_shape(ValueType.DATETIME, datetime(2026, 1, 1))
        validate_type_shape(ValueType.DATETIME, _NOW)

    def test_multi_enum_requires_nonempty_str_sequence(self):
        validate_type_shape(ValueType.MULTI_ENUM, ("a", "b"))
        with pytest.raises(ConfigurationInvalidValueError):
            validate_type_shape(ValueType.MULTI_ENUM, ())
        with pytest.raises(ConfigurationInvalidValueError):
            validate_type_shape(ValueType.MULTI_ENUM, ("a", ""))

    def test_json_schema_requires_dict(self):
        validate_type_shape(ValueType.JSON_SCHEMA, {"a": 1})
        with pytest.raises(ConfigurationInvalidValueError):
            validate_type_shape(ValueType.JSON_SCHEMA, "[]")

    def test_color_token_rejects_hex_literal(self):
        with pytest.raises(ConfigurationInvalidValueError):
            validate_type_shape(ValueType.COLOR_TOKEN, "#1F3B2E")

    def test_color_token_accepts_dotted_token(self):
        validate_type_shape(ValueType.COLOR_TOKEN, "brand.primary")

    def test_color_token_rejects_non_dotted(self):
        with pytest.raises(ConfigurationInvalidValueError):
            validate_type_shape(ValueType.COLOR_TOKEN, "primary")

    def test_reference_types_require_nonempty_string(self):
        for value_type in (
            ValueType.UUID_REFERENCE, ValueType.SECRET_REFERENCE,
            ValueType.FILE_REFERENCE, ValueType.TEMPLATE_REFERENCE, ValueType.DEVICE_REFERENCE,
        ):
            validate_type_shape(value_type, "some-reference-name")
            with pytest.raises(ConfigurationInvalidValueError):
                validate_type_shape(value_type, "")


class TestAuthorizationGrant:
    """SET-1 — the immutable hot-authorization audit record."""

    def _grant(self, **overrides) -> AuthorizationGrant:
        kwargs = dict(
            permission_code="DOCUMENTOS.plantilla.aprobar", requested_by="editor-1",
            authorized_by="reviewer-2", operation_id=new_uuid(), reason="Aprobación de plantilla",
        )
        kwargs.update(overrides)
        return AuthorizationGrant(**kwargs)

    def test_builds_with_valid_fields(self):
        grant = self._grant()
        assert grant.requested_by == "editor-1"
        assert grant.authorized_by == "reviewer-2"
        assert grant.device_id is None

    def test_requires_permission_code(self):
        with pytest.raises(ConfigurationInvalidValueError):
            self._grant(permission_code="")

    def test_requires_requested_by(self):
        with pytest.raises(ConfigurationInvalidValueError):
            self._grant(requested_by="")

    def test_requires_authorized_by(self):
        with pytest.raises(ConfigurationInvalidValueError):
            self._grant(authorized_by="")

    def test_requires_operation_id(self):
        with pytest.raises(ConfigurationInvalidValueError):
            self._grant(operation_id="")

    def test_requires_nonblank_reason(self):
        with pytest.raises(ConfigurationInvalidValueError):
            self._grant(reason="   ")

    def test_is_frozen(self):
        grant = self._grant()
        with pytest.raises(Exception):
            grant.reason = "otro"
