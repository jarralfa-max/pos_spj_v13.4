"""Catch-weight value objects (§17, §18).

Meat/poultry lines track pieces AND real weight at once; neither is derived from
the other. A ``WeightReading`` is a single capture (from a scale or an authorized
manual entry) carrying gross/tare/net, stability and provenance. A
``CatchWeightPosition`` pairs pieces with total weight for a stock line.

Decimal-only; float is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.inventory.enums import WeightCaptureSource
from backend.domain.inventory.exceptions import InvalidCatchWeightError


def _dec(value) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidCatchWeightError("No se permite float en peso/piezas")
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError) as exc:  # pragma: no cover - defensive
        raise InvalidCatchWeightError(f"Valor inválido: {value!r}") from exc


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class WeightReading:
    gross: Decimal
    tare: Decimal = Decimal("0")
    unit: str = "KG"
    stable: bool = True
    source: WeightCaptureSource = WeightCaptureSource.SCALE
    device_id: str | None = None
    captured_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "gross", _dec(self.gross))
        object.__setattr__(self, "tare", _dec(self.tare))
        if self.gross < 0 or self.tare < 0:
            raise InvalidCatchWeightError("Peso bruto/tara no pueden ser negativos")
        if self.tare > self.gross:
            raise InvalidCatchWeightError("La tara no puede exceder el peso bruto")
        if not self.unit:
            raise InvalidCatchWeightError("La lectura de peso requiere unidad")
        if not self.captured_at:
            object.__setattr__(self, "captured_at", _utcnow())

    @property
    def net(self) -> Decimal:
        return self.gross - self.tare


@dataclass(frozen=True, slots=True)
class CatchWeightPosition:
    pieces: Decimal
    weight: Decimal
    weight_unit: str = "KG"
    piece_unit: str = "PZA"

    def __post_init__(self) -> None:
        object.__setattr__(self, "pieces", _dec(self.pieces))
        object.__setattr__(self, "weight", _dec(self.weight))
        if self.pieces < 0 or self.weight < 0:
            raise InvalidCatchWeightError("Piezas y peso deben ser no negativos")

    @property
    def average_weight(self) -> Decimal | None:
        if self.pieces == 0:
            return None
        return self.weight / self.pieces
