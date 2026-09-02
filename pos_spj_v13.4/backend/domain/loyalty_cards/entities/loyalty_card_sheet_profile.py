"""LoyaltyCardSheetProfile — a physical print-sheet stock definition (master
prompt §38-40, "Pliegos 12×18"). All dimensions are Decimal millimeters —
REGLA CERO applies to physical measurements exactly as it does to money.

The phase's own reference size, 12×18 inches, is never hardcoded as a raw
millimeter literal — `standard_12x18()` derives it from the real unit
conversion (`Decimal("12") * MM_PER_INCH`) so the conversion factor is
visible and auditable, not a magic number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.loyalty_cards.enums import SheetOrientation
from backend.domain.loyalty_cards.exceptions import InvalidSheetProfileError
from backend.shared.ids import new_uuid

MM_PER_INCH = Decimal("25.4")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _positive(value: Decimal, field_name: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise InvalidSheetProfileError(f"{field_name} debe ser Decimal, nunca float")
    parsed = Decimal(str(value))
    if parsed <= 0:
        raise InvalidSheetProfileError(f"{field_name} debe ser positivo")
    return parsed


def _non_negative(value: Decimal, field_name: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise InvalidSheetProfileError(f"{field_name} debe ser Decimal, nunca float")
    parsed = Decimal(str(value))
    if parsed < 0:
        raise InvalidSheetProfileError(f"{field_name} no puede ser negativo")
    return parsed


@dataclass(slots=True)
class LoyaltyCardSheetProfile:
    id: str
    code: str
    name: str
    width_mm: Decimal
    height_mm: Decimal
    orientation: SheetOrientation = SheetOrientation.PORTRAIT
    margin_top_mm: Decimal = Decimal("0")
    margin_bottom_mm: Decimal = Decimal("0")
    margin_left_mm: Decimal = Decimal("0")
    margin_right_mm: Decimal = Decimal("0")
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.code or not self.code.strip():
            raise InvalidSheetProfileError("code es obligatorio")
        if not self.name or not self.name.strip():
            raise InvalidSheetProfileError("name es obligatorio")
        self.width_mm = _positive(self.width_mm, "width_mm")
        self.height_mm = _positive(self.height_mm, "height_mm")
        self.margin_top_mm = _non_negative(self.margin_top_mm, "margin_top_mm")
        self.margin_bottom_mm = _non_negative(self.margin_bottom_mm, "margin_bottom_mm")
        self.margin_left_mm = _non_negative(self.margin_left_mm, "margin_left_mm")
        self.margin_right_mm = _non_negative(self.margin_right_mm, "margin_right_mm")
        if self.margin_left_mm + self.margin_right_mm >= self.width_mm:
            raise InvalidSheetProfileError(
                "Los márgenes horizontales dejan cero área imprimible")
        if self.margin_top_mm + self.margin_bottom_mm >= self.height_mm:
            raise InvalidSheetProfileError(
                "Los márgenes verticales dejan cero área imprimible")

    @classmethod
    def create(cls, code: str, name: str, width_mm: Decimal, height_mm: Decimal,
               **kwargs) -> "LoyaltyCardSheetProfile":
        return cls(id=new_uuid(), code=code.strip(), name=name.strip(),
                    width_mm=width_mm, height_mm=height_mm, **kwargs)

    @classmethod
    def standard_12x18(cls, code: str = "SHEET-12X18",
                        name: str = "Pliego 12x18 pulgadas") -> "LoyaltyCardSheetProfile":
        """§38-40's own reference sheet size — 12x18 inches converted to mm
        from the real conversion factor, not a hardcoded mm literal."""
        return cls.create(code, name, Decimal("12") * MM_PER_INCH, Decimal("18") * MM_PER_INCH)

    def printable_width_mm(self) -> Decimal:
        return self.width_mm - self.margin_left_mm - self.margin_right_mm

    def printable_height_mm(self) -> Decimal:
        return self.height_mm - self.margin_top_mm - self.margin_bottom_mm

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self.updated_at = _utcnow()
