"""Typed `ConfigurationValue.value` <-> JSON TEXT round-trip.

One JSON shape per `ValueType`, matching
`backend/domain/settings/value_objects/configuration_value_object.py`'s
type-shape contract. Decimal-valued types (DECIMAL/MONEY/PERCENT) are
always serialized as a JSON *string* (never a JSON number) so re-parsing
never round-trips through `float` and silently loses precision.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from backend.domain.settings.enums import ValueType

_DECIMAL_TYPES = (ValueType.DECIMAL, ValueType.MONEY, ValueType.PERCENT)
_PLAIN_JSON_TYPES = (
    ValueType.BOOLEAN, ValueType.STRING, ValueType.INTEGER, ValueType.ENUM,
    ValueType.JSON_SCHEMA, ValueType.UUID_REFERENCE, ValueType.SECRET_REFERENCE,
    ValueType.FILE_REFERENCE, ValueType.COLOR_TOKEN, ValueType.TEMPLATE_REFERENCE,
    ValueType.DEVICE_REFERENCE,
)


def serialize_value(value_type: ValueType, value: object) -> str:
    if value_type in _PLAIN_JSON_TYPES:
        return json.dumps(value)
    if value_type is ValueType.MULTI_ENUM:
        return json.dumps(list(value))
    if value_type in _DECIMAL_TYPES:
        return json.dumps(str(value))
    if value_type in (ValueType.DATE, ValueType.TIME, ValueType.DATETIME):
        return json.dumps(value.isoformat())
    if value_type is ValueType.DURATION:
        return json.dumps(value.total_seconds())
    raise ValueError(f"Tipo de valor no soportado para serialización: {value_type!r}")


def deserialize_value(value_type: ValueType, raw: str) -> object:
    data = json.loads(raw)
    if value_type in _PLAIN_JSON_TYPES:
        return data
    if value_type is ValueType.MULTI_ENUM:
        return tuple(data)
    if value_type in _DECIMAL_TYPES:
        return Decimal(data)
    if value_type is ValueType.DATE:
        return date.fromisoformat(data)
    if value_type is ValueType.TIME:
        return time.fromisoformat(data)
    if value_type is ValueType.DATETIME:
        return datetime.fromisoformat(data)
    if value_type is ValueType.DURATION:
        return timedelta(seconds=data)
    raise ValueError(f"Tipo de valor no soportado para deserialización: {value_type!r}")
