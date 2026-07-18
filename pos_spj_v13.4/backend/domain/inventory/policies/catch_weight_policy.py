"""CatchWeightPolicy — validate weight captures (§17, §18).

Pure domain logic:
- an unstable scale reading may not be auto-added;
- a net weight must fall within the configured min/max range;
- the piece average must stay within tolerance of an expected average;
- a manual capture outside range requires an explicit authorization.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.inventory.exceptions import (
    InvalidCatchWeightError,
    ManualWeightAuthorizationRequiredError,
)
from backend.domain.inventory.value_objects.catch_weight import WeightReading


def _dec(value) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidCatchWeightError("No se permite float en peso")
    return Decimal(str(value))


class CatchWeightPolicy:
    def enforce_stable_for_auto(self, reading: WeightReading) -> None:
        if not reading.stable:
            raise InvalidCatchWeightError(
                "No se puede agregar automáticamente un peso inestable")

    def is_in_range(self, net, *, min_weight=None, max_weight=None) -> bool:
        net = _dec(net)
        if min_weight is not None and net < _dec(min_weight):
            return False
        if max_weight is not None and net > _dec(max_weight):
            return False
        return True

    def enforce_in_range(self, net, *, min_weight=None, max_weight=None) -> None:
        if not self.is_in_range(net, min_weight=min_weight, max_weight=max_weight):
            raise InvalidCatchWeightError(
                f"Peso {net} fuera del rango permitido "
                f"[{min_weight}, {max_weight}]")

    def enforce_average_within_tolerance(self, *, pieces, total_weight, expected_avg,
                                         tolerance_pct) -> None:
        pieces = _dec(pieces)
        if pieces <= 0:
            raise InvalidCatchWeightError("Piezas debe ser mayor que cero")
        avg = _dec(total_weight) / pieces
        expected = _dec(expected_avg)
        tol = expected * _dec(tolerance_pct) / Decimal("100")
        if abs(avg - expected) > tol:
            raise InvalidCatchWeightError(
                f"Peso promedio {avg} fuera de tolerancia de {expected} ±{tol}")

    def enforce_manual_capture(self, net, *, min_weight=None, max_weight=None,
                               authorized: bool = False) -> None:
        """A manual weight outside range needs an authorization (§18, §47)."""
        if self.is_in_range(net, min_weight=min_weight, max_weight=max_weight):
            return
        if not authorized:
            raise ManualWeightAuthorizationRequiredError(
                "La captura manual fuera de rango requiere autorización")
