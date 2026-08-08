"""Inventory action dialogs (P0-B/P0-D pilot — Cuarentena).

Presentation-only: capture values for the Cuarentena use cases (open, dispose).
No business logic, no backend calls — the page reads the captured values and
hands them to the presenter after the dialog is accepted. Product selection
goes through the canonical search provider (§P0-D) — never a hand-typed UUID.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QComboBox

from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.entity_search_input import EntitySearchInput
from frontend.desktop.components.text_inputs import StandardTextArea
from frontend.desktop.modules.inventory.view_models import QUARANTINE_REASON_ES


class DisposeQuarantineDialog(FormDialog):
    """Motivo de disposición (baja definitiva) de una cuarentena — auditado."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Disponer cuarentena")
        self.reason_input = StandardTextArea(self, placeholder="Motivo de la disposición…")
        self.reason_input.setMaximumHeight(90)
        self.form.addRow("Motivo:", self.reason_input)
        self.add_button_box(ok_text="Disponer")

    def reason(self) -> str:
        return self.reason_input.value()


class OpenQuarantineDialog(FormDialog):
    """Poner stock en cuarentena: producto (búsqueda canónica), motivo, cantidad."""

    def __init__(self, parent=None, *, product_provider) -> None:
        super().__init__(parent, title="Nueva cuarentena")
        self.product = EntitySearchInput(
            self, provider=product_provider,
            placeholder="Buscar producto por nombre, código o código de barras…")
        self.reason_combo = QComboBox(self)
        for code, label in QUARANTINE_REASON_ES.items():
            self.reason_combo.addItem(label, code)
        self.quantity = DecimalInput(self, precision=3, minimum="0.001")
        self.note_input = StandardTextArea(self, placeholder="Nota (opcional)…")
        self.note_input.setMaximumHeight(70)
        self.form.addRow("Producto:", self.product)
        self.form.addRow("Motivo:", self.reason_combo)
        self.form.addRow("Cantidad:", self.quantity)
        self.form.addRow("Nota:", self.note_input)
        self.add_button_box(ok_text="Poner en cuarentena")

    def product_id(self) -> str | None:
        return self.product.selected_id()

    def reason_code(self) -> str:
        return str(self.reason_combo.currentData() or "")

    def quantity_value(self):
        return self.quantity.decimal_value()

    def note(self) -> str:
        return self.note_input.value()
