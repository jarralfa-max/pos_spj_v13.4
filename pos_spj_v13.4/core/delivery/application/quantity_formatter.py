"""QuantityFormatter — formats a Decimal quantity with its proper unit label.

Never hardcodes unit strings. All labels come from UNIT_LABELS_ES so there
is a single source of truth for the Spanish unit display strings.
"""
from __future__ import annotations

from decimal import Decimal

from core.delivery.domain.value_objects import UNIT_LABELS_ES, WEIGHABLE_UNITS, UnitCode


class QuantityFormatter:
    """Format a quantity+unit pair into a human-readable Spanish string."""

    @staticmethod
    def format(qty: Decimal, unit_code: UnitCode) -> str:
        """Format qty with its real unit label. Never hardcodes 'kg'.

        Weighable units (kg, g, L) show up to 3 decimal places with trailing
        zeros stripped.  Countable units (pza, unidad, caja, paquete) show
        as integers when the value is whole.

        Examples:
            format(Decimal("0.750"), UnitCode.KILOGRAM)  -> "0.75 kg"
            format(Decimal("1.000"), UnitCode.KILOGRAM)  -> "1 kg"
            format(Decimal("3"),     UnitCode.PIECE)     -> "3 pza"
            format(Decimal("2.5"),   UnitCode.PIECE)     -> "2.5 pza"
            format(Decimal("1.5"),   UnitCode.LITER)     -> "1.5 L"
        """
        label = UNIT_LABELS_ES.get(unit_code, str(unit_code.value))

        if unit_code in WEIGHABLE_UNITS:
            formatted = f"{qty:.3f}".rstrip("0").rstrip(".")
        else:
            formatted = (
                str(int(qty))
                if qty == qty.to_integral_value()
                else str(qty)
            )

        return f"{formatted} {label}"
