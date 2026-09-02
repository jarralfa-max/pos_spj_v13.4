"""Typed value coercion for `ConfigurationValue.value` — one Python shape
per `ValueType` (§8). Pure type-shape validation only; allowed-values and
schema-constraint checks live in
`policies/configuration_validation_policy.py`, which composes this module.

No `float` anywhere (project-wide rule): money/percent/decimal values are
`Decimal`, never `float`.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from backend.domain.settings.enums import ValueType
from backend.domain.settings.exceptions import ConfigurationInvalidValueError

# COLOR_TOKEN must be a dotted lowercase design-system token (e.g.
# "brand.primary", "status.success") — never a raw hex literal (§51: "No
# permitir colores hexadecimales dentro de páginas").
_HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{3}([0-9a-fA-F]{3}([0-9a-fA-F]{2})?)?$")
_COLOR_TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


def _is_strict_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int)


def _validate_string_like(value_type: ValueType, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationInvalidValueError(
            f"{value_type.value} requiere una cadena no vacía, recibido {value!r}"
        )


def validate_type_shape(value_type: ValueType, value: object) -> None:
    """Raise `ConfigurationInvalidValueError` unless `value` has the Python
    shape `value_type` requires. Does not check allowed_values/ranges."""
    if value_type is ValueType.BOOLEAN:
        if not isinstance(value, bool):
            raise ConfigurationInvalidValueError(f"BOOLEAN requiere bool, recibido {value!r}")
        return

    if value_type is ValueType.STRING:
        if not isinstance(value, str):
            raise ConfigurationInvalidValueError(f"STRING requiere str, recibido {value!r}")
        return

    if value_type is ValueType.INTEGER:
        if not _is_strict_int(value):
            raise ConfigurationInvalidValueError(f"INTEGER requiere int, recibido {value!r}")
        return

    if value_type in (ValueType.DECIMAL, ValueType.MONEY, ValueType.PERCENT):
        from decimal import Decimal
        if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, Decimal):
            raise ConfigurationInvalidValueError(
                f"{value_type.value} requiere Decimal (nunca float), recibido {value!r}"
            )
        return

    if value_type is ValueType.DATE:
        if not isinstance(value, date) or isinstance(value, datetime):
            raise ConfigurationInvalidValueError(f"DATE requiere date, recibido {value!r}")
        return

    if value_type is ValueType.TIME:
        if not isinstance(value, time):
            raise ConfigurationInvalidValueError(f"TIME requiere time, recibido {value!r}")
        return

    if value_type is ValueType.DATETIME:
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ConfigurationInvalidValueError(
                f"DATETIME requiere datetime con zona horaria, recibido {value!r}"
            )
        return

    if value_type is ValueType.DURATION:
        if not isinstance(value, timedelta):
            raise ConfigurationInvalidValueError(f"DURATION requiere timedelta, recibido {value!r}")
        return

    if value_type is ValueType.ENUM:
        _validate_string_like(value_type, value)
        return

    if value_type is ValueType.MULTI_ENUM:
        if not isinstance(value, (tuple, list)) or not value or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise ConfigurationInvalidValueError(
                f"MULTI_ENUM requiere una secuencia no vacía de str, recibido {value!r}"
            )
        return

    if value_type is ValueType.JSON_SCHEMA:
        if not isinstance(value, dict):
            raise ConfigurationInvalidValueError(f"JSON_SCHEMA requiere dict, recibido {value!r}")
        return

    if value_type is ValueType.COLOR_TOKEN:
        _validate_string_like(value_type, value)
        if _HEX_COLOR_PATTERN.match(value.strip()):
            raise ConfigurationInvalidValueError(
                "COLOR_TOKEN no admite literales hexadecimales — usar un token del "
                "tema (p. ej. 'brand.primary'), nunca '#RRGGBB' (§51)."
            )
        if not _COLOR_TOKEN_PATTERN.match(value.strip()):
            raise ConfigurationInvalidValueError(
                f"COLOR_TOKEN debe ser un token con puntos en minúsculas, recibido {value!r}"
            )
        return

    # UUID_REFERENCE, SECRET_REFERENCE, FILE_REFERENCE, TEMPLATE_REFERENCE,
    # DEVICE_REFERENCE: all reference something else by string id/name.
    # SECRET_REFERENCE is the *name* used to look up the raw secret in
    # SecretStoreGateway — never the raw secret itself (§46).
    _validate_string_like(value_type, value)
