"""ImpositionPolicy — pure geometry for laying cards out on a sheet (master
prompt §38-40). No IO, no entities — plain Decimal arithmetic, so both the
`LoyaltyCardImpositionProfile` entity and any future preview/report can
call it directly."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.loyalty_cards.exceptions import CardDoesNotFitOnSheetError


@dataclass(frozen=True, slots=True)
class ImpositionResult:
    columns: int
    rows: int

    @property
    def cards_per_sheet(self) -> int:
        return self.columns * self.rows


class ImpositionPolicy:
    @staticmethod
    def compute(
        *, printable_width_mm: Decimal, printable_height_mm: Decimal,
        card_width_mm: Decimal, card_height_mm: Decimal, bleed_mm: Decimal,
        gutter_horizontal_mm: Decimal, gutter_vertical_mm: Decimal,
    ) -> ImpositionResult:
        """Each card occupies (card + 2*bleed) plus one gutter gap to its
        neighbor — the layout is `col * (cell + gutter) - gutter <=
        printable`, i.e. floor((printable + gutter) / (cell + gutter))."""
        cell_width = card_width_mm + (bleed_mm * 2)
        cell_height = card_height_mm + (bleed_mm * 2)

        columns = int((printable_width_mm + gutter_horizontal_mm) // (cell_width + gutter_horizontal_mm))
        rows = int((printable_height_mm + gutter_vertical_mm) // (cell_height + gutter_vertical_mm))

        if columns <= 0 or rows <= 0:
            raise CardDoesNotFitOnSheetError(
                "La tarjeta (con sangrado/calle) no cabe en el área imprimible del pliego")
        return ImpositionResult(columns=columns, rows=rows)
