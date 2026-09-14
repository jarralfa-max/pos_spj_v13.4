"""Weight uses the canonical numeric validation and zero initial value."""
from frontend.desktop.components.quantity_input import QuantityInput


class WeightInput(QuantityInput):
    def __init__(self, parent=None, *, decimals=3):
        super().__init__(parent, decimals=decimals)
        self.setObjectName("weightInput")
        self.setAccessibleName("Peso en kilogramos")
        self.setSuffix(" kg")
