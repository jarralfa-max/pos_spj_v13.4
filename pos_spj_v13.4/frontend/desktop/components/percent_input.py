"""Percent input component for rates and discounts."""

from __future__ import annotations

from frontend.desktop.components.numeric_input import NumericInput


class PercentInput(NumericInput):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, decimals=2, minimum=0.0, maximum=100.0)
        self.setSuffix(" %")
