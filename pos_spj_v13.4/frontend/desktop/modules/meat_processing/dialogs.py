"""Procesamiento Cárnico action dialogs (PROC-23). Presentation-only: capture
values for the corresponding use cases — no business logic, no backend
calls. Mirrors frontend/desktop/modules/inventory/dialogs.py.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QComboBox

from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.product_search_box import ProductSearchBox


class CreateProcessingOrderDialog(FormDialog):
    """Nueva orden de procesamiento: tipo de proceso, producto objetivo
    (búsqueda canónica — nunca un UUID tecleado a mano) y cantidad/peso
    planeados."""

    def __init__(self, parent=None, *, process_types, product_provider,
                 empty_reason_provider=None) -> None:
        super().__init__(parent, title="Nueva orden de procesamiento")
        self.process_type_combo = QComboBox(self)
        for code, label in process_types:
            self.process_type_combo.addItem(label, code)
        # Búsqueda estándar de productos; qué productos ofrece depende del
        # proceso elegido (formular busca lo que se fabrica; despiezar, empacar
        # o acondicionar, la entrada).
        self.product = ProductSearchBox(
            self, provider=lambda q: product_provider(q, self.process_type()),
            empty_reason_provider=(
                None if empty_reason_provider is None
                else lambda q: empty_reason_provider(q, self.process_type())))
        self.process_type_combo.currentIndexChanged.connect(
            lambda _i: self.product.clear())
        self.quantity = DecimalInput(self, precision=3, minimum="0")
        self.weight = DecimalInput(self, precision=3, minimum="0", suffix="kg")
        self.form.addRow("Tipo de proceso:", self.process_type_combo)
        self.form.addRow("Producto objetivo:", self.product)
        self.form.addRow("Cantidad planeada:", self.quantity)
        self.form.addRow("Peso planeado:", self.weight)
        self.add_button_box(ok_text="Crear orden")

    def process_type(self) -> str:
        return str(self.process_type_combo.currentData() or "")

    def product_id(self) -> str | None:
        opcion = self.product.selected_option()
        return opcion.id if opcion is not None else None

    def planned_quantity(self):
        return self.quantity.decimal_value()

    def planned_weight(self):
        return self.weight.decimal_value()
