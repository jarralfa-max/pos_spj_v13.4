"""Configuration-fed limits; this policy intentionally has no hard-coded amounts."""
from decimal import Decimal

from ..exceptions import TransferLimitExceededError


def _decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("Transfer limits must be Decimal")
    return Decimal(str(value))


class TransferLimitPolicy:
    def __init__(self, *, max_quantity: Decimal | str | int | None = None,
                 max_weight: Decimal | str | int | None = None,
                 max_reference_value: Decimal | str | int | None = None) -> None:
        self._max_quantity = _decimal(max_quantity) if max_quantity is not None else None
        self._max_weight = _decimal(max_weight) if max_weight is not None else None
        self._max_reference_value = _decimal(max_reference_value) if max_reference_value is not None else None

    def require_within_limits(self, *, quantity: Decimal | str | int,
                              weight: Decimal | str | int,
                              reference_value: Decimal | str | int = 0) -> None:
        values = ((_decimal(quantity), self._max_quantity, "cantidad"),
                  (_decimal(weight), self._max_weight, "peso"),
                  (_decimal(reference_value), self._max_reference_value, "valor referencial"))
        for actual, maximum, label in values:
            if maximum is not None and actual > maximum:
                raise TransferLimitExceededError(f"El {label} excede el límite configurado")
