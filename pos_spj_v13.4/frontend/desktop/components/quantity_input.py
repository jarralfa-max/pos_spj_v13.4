"""Quantity input component for products and inventory operations."""

from __future__ import annotations

from frontend.desktop.components.numeric_input import NumericInput


class QuantityInput(NumericInput):
    def __init__(self, parent=None, *, decimals: int = 3) -> None:
        super().__init__(parent, decimals=decimals, minimum=0.0, maximum=999999999.0)
