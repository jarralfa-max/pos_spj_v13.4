"""Money input component with Spanish-friendly currency formatting."""

from __future__ import annotations

from frontend.desktop.components.numeric_input import NumericInput


class MoneyInput(NumericInput):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, decimals=2, minimum=0.0, maximum=999999999.0)
        self.setPrefix("$ ")
