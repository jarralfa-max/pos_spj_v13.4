"""Price-variance policy (migrated from the legacy monolith's cost-variance alert).

The legacy `compras_pro.py` compared a captured unit cost against a historical
cost (precio_compra → costo_promedio) with float math and a hardcoded 20% magic
number, then wrote an audit row. This is a pure, Decimal-based domain policy: it
computes the variation and decides whether it is significant. The threshold is
configurable (default 20%), never hardcoded in the widget.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from backend.domain.procurement.exceptions import ProcurementDomainError

DEFAULT_VARIANCE_THRESHOLD = Decimal("20")  # percent


class PriceDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"


@dataclass(frozen=True, slots=True)
class PriceVarianceResult:
    historical_cost: Decimal
    captured_cost: Decimal
    percent: Decimal            # absolute variation, e.g. 25.0
    direction: PriceDirection
    is_significant: bool

    def label(self) -> str:
        """es-MX label mirroring the legacy '▲ SUBIÓ 25.0%' / '▼ BAJÓ 10.0%'."""
        if self.direction is PriceDirection.FLAT:
            return "—"
        arrow = "▲" if self.direction is PriceDirection.UP else "▼"
        verb = "SUBIÓ" if self.direction is PriceDirection.UP else "BAJÓ"
        return f"{arrow} {verb} {self.percent:.1f}%"


class PriceVariancePolicy:
    def __init__(self, *, threshold_percent: Decimal | str | None = None) -> None:
        threshold = (DEFAULT_VARIANCE_THRESHOLD if threshold_percent is None
                     else Decimal(str(threshold_percent)))
        if threshold < 0:
            raise ProcurementDomainError("El umbral de variación no puede ser negativo")
        self._threshold = threshold

    @property
    def threshold_percent(self) -> Decimal:
        return self._threshold

    def evaluate(self, historical_cost, captured_cost) -> PriceVarianceResult:
        historical = _dec(historical_cost)
        captured = _dec(captured_cost)
        if historical <= 0 or captured <= 0:
            # No comparable baseline (legacy behaviour: no alert, shows "—").
            return PriceVarianceResult(historical, captured, Decimal("0"),
                                       PriceDirection.FLAT, False)
        delta = captured - historical
        percent = (abs(delta) / historical) * Decimal("100")
        if delta > 0:
            direction = PriceDirection.UP
        elif delta < 0:
            direction = PriceDirection.DOWN
        else:
            direction = PriceDirection.FLAT
        return PriceVarianceResult(historical, captured, percent, direction,
                                   percent >= self._threshold)


def _dec(value) -> Decimal:
    if isinstance(value, float):
        raise ProcurementDomainError("No se permite float en costos; usa Decimal/str")
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))
