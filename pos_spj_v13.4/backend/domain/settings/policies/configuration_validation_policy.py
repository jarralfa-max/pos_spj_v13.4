"""ConfigurationValidationPolicy — is this raw value legal for this
definition? (§8-9). Composes the pure type-shape check
(`value_objects/configuration_value_object.py`) with allowed_values and
`validation_schema` range/pattern constraints.

`validation_schema` is an intentionally small, explicit dict of
constraints (not a full JSON-Schema implementation — YAGNI until a real
definition needs more): recognized keys are ``min``, ``max``,
``min_length``, ``max_length``, ``pattern``.
"""

from __future__ import annotations

import re
from decimal import Decimal

from backend.domain.settings.enums import ValueType
from backend.domain.settings.exceptions import ConfigurationInvalidValueError
from backend.domain.settings.value_objects.configuration_value_object import validate_type_shape

_ORDERABLE_TYPES = (
    ValueType.INTEGER, ValueType.DECIMAL, ValueType.MONEY, ValueType.PERCENT,
    ValueType.DATE, ValueType.TIME, ValueType.DATETIME, ValueType.DURATION,
)
_SIZED_TYPES = (ValueType.STRING, ValueType.MULTI_ENUM)


def validate_allowed_values(value_type: ValueType, value: object, allowed_values: tuple[str, ...] | None) -> None:
    if allowed_values is None:
        return
    if value_type is ValueType.MULTI_ENUM:
        offending = [item for item in value if item not in allowed_values]
        if offending:
            raise ConfigurationInvalidValueError(f"Valores fuera de allowed_values: {offending}")
        return
    if value not in allowed_values:
        raise ConfigurationInvalidValueError(f"{value!r} no está en allowed_values {allowed_values}")


def validate_schema_constraints(value_type: ValueType, value: object, validation_schema: dict | None) -> None:
    if not validation_schema:
        return

    if "min" in validation_schema and value_type in _ORDERABLE_TYPES:
        floor = validation_schema["min"]
        if isinstance(floor, (int, float)) and not isinstance(floor, Decimal) and value_type in (
            ValueType.DECIMAL, ValueType.MONEY, ValueType.PERCENT,
        ):
            floor = Decimal(str(floor))
        if value < floor:
            raise ConfigurationInvalidValueError(f"{value!r} es menor que el mínimo permitido {floor!r}")

    if "max" in validation_schema and value_type in _ORDERABLE_TYPES:
        ceiling = validation_schema["max"]
        if isinstance(ceiling, (int, float)) and not isinstance(ceiling, Decimal) and value_type in (
            ValueType.DECIMAL, ValueType.MONEY, ValueType.PERCENT,
        ):
            ceiling = Decimal(str(ceiling))
        if value > ceiling:
            raise ConfigurationInvalidValueError(f"{value!r} excede el máximo permitido {ceiling!r}")

    if "min_length" in validation_schema and value_type in _SIZED_TYPES:
        if len(value) < validation_schema["min_length"]:
            raise ConfigurationInvalidValueError(
                f"Longitud {len(value)} menor que min_length={validation_schema['min_length']}"
            )

    if "max_length" in validation_schema and value_type in _SIZED_TYPES:
        if len(value) > validation_schema["max_length"]:
            raise ConfigurationInvalidValueError(
                f"Longitud {len(value)} mayor que max_length={validation_schema['max_length']}"
            )

    if "pattern" in validation_schema and value_type is ValueType.STRING:
        if not re.fullmatch(validation_schema["pattern"], value):
            raise ConfigurationInvalidValueError(
                f"{value!r} no cumple el patrón {validation_schema['pattern']!r}"
            )


def validate_value(
    value_type: ValueType, value: object, *,
    allowed_values: tuple[str, ...] | None = None,
    validation_schema: dict | None = None,
) -> None:
    """Full check: type shape, then allowed_values, then schema constraints."""
    validate_type_shape(value_type, value)
    validate_allowed_values(value_type, value, allowed_values)
    validate_schema_constraints(value_type, value, validation_schema)


def validate_against_definition(definition, value: object) -> None:
    """Convenience entry point taking a `ConfigurationDefinition` directly."""
    validate_value(
        definition.value_type, value,
        allowed_values=definition.allowed_values,
        validation_schema=definition.validation_schema,
    )
