from decimal import Decimal

from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError
from backend.shared.ids import validate_uuidv7


def required_uuid(value: str, field_name: str) -> str:
    try:
        return validate_uuidv7(value)
    except ValueError as exc:
        raise MeatProcessingInvariantError(f"{field_name} debe ser UUIDv7") from exc


def optional_uuid(value: str | None, field_name: str) -> str | None:
    return None if value is None else required_uuid(value, field_name)


def decimal_value(value, field_name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{field_name} debe usar Decimal, nunca float")
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise MeatProcessingInvariantError(f"{field_name} no es decimal válido") from exc


def optional_decimal_value(value, field_name: str) -> Decimal | None:
    return None if value is None else decimal_value(value, field_name)
