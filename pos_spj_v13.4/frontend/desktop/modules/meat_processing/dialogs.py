"""Procesamiento Cárnico action dialogs (PROC-23). Presentation-only: capture
values for the corresponding use cases — no business logic, no backend
calls. Mirrors frontend/desktop/modules/inventory/dialogs.py.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QComboBox, QDialogButtonBox, QLabel

from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.product_search_box import ProductSearchBox


class CreateProcessingOrderDialog(FormDialog):
    """Nueva orden de procesamiento: tipo de proceso, producto objetivo
    (búsqueda canónica — nunca un UUID tecleado a mano) y cantidad/peso
    planeados.

    Auditoría de Producción 32cfbf P0 (2026-10-16): el producto se RETIENE al
    elegirlo (clic o Intro) en vez de leerse del renglón resaltado al cerrar, y
    el diálogo no se acepta incompleto: antes se cerraba y avisaba después,
    perdiendo lo capturado. Lo que impide crear cualquier orden (sin almacén de
    producción) se dice al abrir, no al final."""

    def __init__(self, parent=None, *, process_types, product_provider,
                 empty_reason_provider=None, blocking_problem: str | None = None) -> None:
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
                else lambda q: empty_reason_provider(q, self.process_type())),
            keep_selection=True)
        self.process_type_combo.currentIndexChanged.connect(
            lambda _i: self.product.clear())
        self.quantity = DecimalInput(self, precision=3, minimum="0")
        self.weight = DecimalInput(self, precision=3, minimum="0", suffix="kg")
        self._blocking = blocking_problem
        if blocking_problem:
            aviso = QLabel(blocking_problem, self)
            aviso.setObjectName("textDanger")
            aviso.setWordWrap(True)
            self.form.addRow(aviso)
        self.form.addRow("Tipo de proceso:", self.process_type_combo)
        self.form.addRow("Producto objetivo:", self.product)
        self.form.addRow("Cantidad planeada:", self.quantity)
        self.form.addRow("Peso planeado:", self.weight)
        self._error = QLabel("", self)
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        self.form.addRow(self._error)
        box = self.add_button_box(ok_text="Crear orden", on_accept=self._accept_if_valid)
        box.button(QDialogButtonBox.Ok).setEnabled(not blocking_problem)

    def process_type(self) -> str:
        return str(self.process_type_combo.currentData() or "")

    def product_id(self) -> str | None:
        opcion = self.product.picked_option()
        return opcion.id if opcion is not None else None

    def problem(self) -> str | None:
        """Qué falta para poder crear la orden, o None."""
        if self._blocking:
            return self._blocking
        if self.product_id() is None:
            return "Elige el producto de la lista (clic o Intro sobre el resultado)."
        if not (self.quantity.decimal_value() or 0) and not (self.weight.decimal_value() or 0):
            return "Captura la cantidad o el peso planeado."
        return None

    def _accept_if_valid(self) -> None:
        problema = self.problem()
        self._error.setText(problema or "")
        if problema is None:
            self.accept()

    def planned_quantity(self):
        return self.quantity.decimal_value()

    def planned_weight(self):
        return self.weight.decimal_value()
