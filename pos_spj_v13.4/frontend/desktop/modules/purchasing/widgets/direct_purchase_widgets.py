"""Design-system based widgets for the direct-purchase workspace."""

from PyQt5.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import SectionCard
from frontend.desktop.themes.tokens import Spacing


class PurchaseProcessStepper(QWidget):
    STEPS = ("Proveedor y destino", "Productos", "Condiciones", "Revisión", "Confirmación")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(Spacing.SM)
        self._labels = []
        for number, title in enumerate(self.STEPS, 1):
            label = QLabel(f"{number}. {title}", self)
            label.setProperty("role", "muted")
            row.addWidget(label, stretch=1)
            self._labels.append(label)
        self.set_current(0)

    def set_current(self, index: int) -> None:
        for position, label in enumerate(self._labels):
            label.setProperty("state", "ACTIVE" if position == index else "PENDING")
            label.style().unpolish(label)
            label.style().polish(label)


class PurchaseSummaryPanel(SectionCard):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Resumen")
        self._values = {}
        form = QFormLayout()
        for key, title in (
            ("supplier", "Proveedor"), ("destination", "Destino"),
            ("payment", "Condición"), ("subtotal", "Subtotal"),
            ("tax", "Impuestos"), ("discount", "Descuento"), ("total", "Total"),
        ):
            value = QLabel("—", self)
            value.setWordWrap(True)
            if key == "total":
                value.setProperty("role", "title")
            form.addRow(title, value)
            self._values[key] = value
        self.body().addLayout(form)
        self.actions = QVBoxLayout()
        self.actions.setSpacing(Spacing.SM)
        self.body().addLayout(self.actions)

    def update_summary(self, **values) -> None:
        for key, value in values.items():
            if key in self._values:
                self._values[key].setText(str(value or "—"))
