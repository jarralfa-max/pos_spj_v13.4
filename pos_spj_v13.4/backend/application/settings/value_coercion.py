"""Convierte lo capturado (texto de un formulario o un valor ya tipado) al tipo
de la definición. Vive en aplicación, no en la UI: la pantalla sólo entrega lo
que el usuario escribió, y aquí se decide si es un valor legal.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from backend.domain.settings.enums import ValueType
from backend.domain.settings.exceptions import ConfigurationInvalidValueError

_TRUE = ("1", "true", "si", "sí", "yes", "verdadero")
_FALSE = ("0", "false", "no", "falso")


def coerce_value(value_type: ValueType, raw: object) -> object:
    if value_type is ValueType.BOOLEAN:
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise ConfigurationInvalidValueError(f"{raw!r} no es un sí/no válido")
    if value_type is ValueType.INTEGER:
        if isinstance(raw, bool):
            raise ConfigurationInvalidValueError("Se esperaba un número entero")
        if isinstance(raw, int):
            return raw
        try:
            number = Decimal(str(raw).strip())
        except (InvalidOperation, ValueError) as exc:
            raise ConfigurationInvalidValueError(f"{raw!r} no es un número entero") from exc
        if number != number.to_integral_value():
            raise ConfigurationInvalidValueError(f"{raw!r} no es un número entero")
        return int(number)
    if value_type in (ValueType.DECIMAL, ValueType.MONEY, ValueType.PERCENT):
        if isinstance(raw, float):
            raise ConfigurationInvalidValueError("Los importes no se capturan como float")
        try:
            return Decimal(str(raw).strip())
        except (InvalidOperation, ValueError) as exc:
            raise ConfigurationInvalidValueError(f"{raw!r} no es un número") from exc
    if value_type is ValueType.JSON_SCHEMA:
        if isinstance(raw, dict):
            return raw
        try:
            data = json.loads(str(raw))
        except ValueError as exc:
            raise ConfigurationInvalidValueError("El valor no es un JSON válido") from exc
        if not isinstance(data, dict):
            raise ConfigurationInvalidValueError("Se esperaba un objeto JSON")
        return data
    if value_type in (ValueType.STRING, ValueType.ENUM):
        return str(raw).strip()
    raise ConfigurationInvalidValueError(f"Tipo {value_type.value} no editable todavía")


def display_value(value_type: ValueType, value: object, *, sensitive: bool = False) -> str:
    """Texto para mostrar un valor; un valor sensible nunca se muestra."""
    if sensitive:
        return "••••••"
    if value is None:
        return "—"
    if value_type is ValueType.BOOLEAN:
        return "Sí" if value else "No"
    if value_type is ValueType.JSON_SCHEMA:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
