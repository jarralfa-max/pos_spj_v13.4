"""LoyaltyCardImpositionProfile — how a specific card size is laid out on a
sheet profile (master prompt §38-40: sangrado/bleed, área de seguridad/safe
area, calles/gutters).

`columns`/`rows`/`cards_per_sheet` are DERIVED via `ImpositionPolicy`, never
accepted as caller-supplied input — a caller cannot claim a layout fits more
cards than the geometry actually allows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.loyalty_cards.exceptions import InvalidImpositionProfileError
from backend.domain.loyalty_cards.policies.imposition_policy import ImpositionPolicy
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _non_negative(value: Decimal, field_name: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise InvalidImpositionProfileError(f"{field_name} debe ser Decimal, nunca float")
    parsed = Decimal(str(value))
    if parsed < 0:
        raise InvalidImpositionProfileError(f"{field_name} no puede ser negativo")
    return parsed


def _positive(value: Decimal, field_name: str) -> Decimal:
    parsed = _non_negative(value, field_name)
    if parsed == 0:
        raise InvalidImpositionProfileError(f"{field_name} debe ser positivo")
    return parsed


@dataclass(slots=True)
class LoyaltyCardImpositionProfile:
    id: str
    sheet_profile_id: str
    card_width_mm: Decimal
    card_height_mm: Decimal
    columns: int
    rows: int
    bleed_mm: Decimal = Decimal("0")
    safe_area_mm: Decimal = Decimal("0")
    gutter_horizontal_mm: Decimal = Decimal("0")
    gutter_vertical_mm: Decimal = Decimal("0")
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.sheet_profile_id:
            raise InvalidImpositionProfileError("sheet_profile_id es obligatorio")
        self.card_width_mm = _positive(self.card_width_mm, "card_width_mm")
        self.card_height_mm = _positive(self.card_height_mm, "card_height_mm")
        self.bleed_mm = _non_negative(self.bleed_mm, "bleed_mm")
        self.safe_area_mm = _non_negative(self.safe_area_mm, "safe_area_mm")
        self.gutter_horizontal_mm = _non_negative(self.gutter_horizontal_mm, "gutter_horizontal_mm")
        self.gutter_vertical_mm = _non_negative(self.gutter_vertical_mm, "gutter_vertical_mm")
        smaller_dimension = min(self.card_width_mm, self.card_height_mm)
        if self.safe_area_mm * 2 >= smaller_dimension:
            raise InvalidImpositionProfileError(
                "safe_area_mm es demasiado grande para el tamaño de tarjeta "
                "(no dejaría área de contenido)")
        if self.columns <= 0 or self.rows <= 0:
            raise InvalidImpositionProfileError("columns/rows deben ser positivos")

    @classmethod
    def create(
        cls, sheet_profile_id: str, *, printable_width_mm: Decimal, printable_height_mm: Decimal,
        card_width_mm: Decimal, card_height_mm: Decimal, bleed_mm: Decimal = Decimal("0"),
        safe_area_mm: Decimal = Decimal("0"), gutter_horizontal_mm: Decimal = Decimal("0"),
        gutter_vertical_mm: Decimal = Decimal("0"),
    ) -> "LoyaltyCardImpositionProfile":
        result = ImpositionPolicy.compute(
            printable_width_mm=Decimal(str(printable_width_mm)),
            printable_height_mm=Decimal(str(printable_height_mm)),
            card_width_mm=Decimal(str(card_width_mm)), card_height_mm=Decimal(str(card_height_mm)),
            bleed_mm=Decimal(str(bleed_mm)), gutter_horizontal_mm=Decimal(str(gutter_horizontal_mm)),
            gutter_vertical_mm=Decimal(str(gutter_vertical_mm)))
        return cls(
            id=new_uuid(), sheet_profile_id=sheet_profile_id, card_width_mm=card_width_mm,
            card_height_mm=card_height_mm, columns=result.columns, rows=result.rows,
            bleed_mm=bleed_mm, safe_area_mm=safe_area_mm, gutter_horizontal_mm=gutter_horizontal_mm,
            gutter_vertical_mm=gutter_vertical_mm)

    @property
    def cards_per_sheet(self) -> int:
        return self.columns * self.rows
