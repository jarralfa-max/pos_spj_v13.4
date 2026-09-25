"""Diálogos del Plan de producción. Sólo capturan; no calculan ni validan
reglas de negocio (lo hacen los casos de uso)."""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QLabel, QSpinBox, QTableWidget, QTableWidgetItem

from frontend.desktop.components.date_input import DateInput
from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.product_search_box import ProductSearchBox


class AddPlanLineDialog(FormDialog):
    """Qué se necesita (producto demandado) y cómo atenderlo (proceso y, en
    despiece, la entrada que se va a despiezar)."""

    def __init__(self, parent=None, *, presenter, prefill: dict | None = None) -> None:
        super().__init__(parent, title="Línea del plan")
        self._presenter = presenter
        prefill = prefill or {}
        self.product = ProductSearchBox(
            self, provider=presenter.product_options,
            empty_reason_provider=lambda q: presenter.product_search_reason(q, producible=True))
        self.process = QComboBox(self)
        for code, label in presenter.process_types():
            self.process.addItem(label, code)
        self.input_label = QLabel("Entrada a despiezar:", self)
        self.input_product = ProductSearchBox(
            self, provider=presenter.input_options,
            empty_reason_provider=lambda q: presenter.product_search_reason(q, producible=False))
        self.weight = DecimalInput(self, precision=3, minimum="0", suffix="kg")
        self.quantity = DecimalInput(self, precision=3, minimum="0")
        self.priority = QSpinBox(self)
        self.priority.setRange(0, 9)
        self.required = DateInput(self)
        self.form.addRow("Producto necesario:", self.product)
        self.form.addRow("Proceso:", self.process)
        self.form.addRow(self.input_label, self.input_product)
        self.form.addRow("Peso a procesar:", self.weight)
        self.form.addRow("Cantidad:", self.quantity)
        self.form.addRow("Prioridad:", self.priority)
        self.form.addRow("Se requiere el:", self.required)
        self._source = prefill.get("source_type", "MANUAL")
        self._reference = prefill.get("source_reference_id")
        self._prefilled_product = prefill.get("product_id")
        if self._prefilled_product:
            self.product.set_selected_label(prefill.get("product_name", ""))
            self.product.setEnabled(False)
        if prefill.get("quantity") is not None:
            self.weight.set_decimal(Decimal(str(prefill["quantity"])))
        self.process.currentIndexChanged.connect(self._sync_input)
        self._sync_input()
        self.add_button_box(ok_text="Agregar al plan")

    def _sync_input(self) -> None:
        visible = self._presenter.needs_input_product(self.process_type())
        self.input_label.setVisible(visible)
        self.input_product.setVisible(visible)

    def process_type(self) -> str:
        return str(self.process.currentData() or "")

    def product_id(self) -> str | None:
        if self._prefilled_product:
            return self._prefilled_product
        opcion = self.product.selected_option()
        return opcion.id if opcion is not None else None

    def values(self) -> dict:
        entrada = self.input_product.selected_option()
        return {
            "product_id": self.product_id(), "process_type": self.process_type(),
            "target_product_id": (entrada.id if entrada is not None and
                                  self._presenter.needs_input_product(self.process_type())
                                  else None),
            "planned_weight": self.weight.decimal_value() or Decimal("0"),
            "planned_quantity": self.quantity.decimal_value() or Decimal("0"),
            "priority": int(self.priority.value()),
            "source_type": self._source, "source_reference_id": self._reference,
        }


class PlanSuggestionsDialog(FormDialog):
    """Sugerencias de una fuente; el planeador marca cuáles pasan al plan."""

    def __init__(self, parent=None, *, title: str, suggestions, note: str | None) -> None:
        super().__init__(parent, title=title, width=720)
        self._suggestions = list(suggestions)
        if note:
            aviso = QLabel(note, self)
            aviso.setWordWrap(True)
            self.form.addRow(aviso)
        self.table = QTableWidget(len(self._suggestions), 3, self)
        self.table.setHorizontalHeaderLabels(["Producto", "Sugerido", "Detalle"])
        for fila, s in enumerate(self._suggestions):
            marca = QTableWidgetItem(s.product_name)
            marca.setFlags(marca.flags() | Qt.ItemIsUserCheckable)
            marca.setCheckState(Qt.Checked)
            self.table.setItem(fila, 0, marca)
            self.table.setItem(fila, 1, QTableWidgetItem(f"{Decimal(s.quantity).normalize():f}"))
            self.table.setItem(fila, 2, QTableWidgetItem(s.detail))
        self.form.addRow(self.table)
        self.add_button_box(ok_text="Agregar las marcadas")

    def chosen(self):
        return [s for fila, s in enumerate(self._suggestions)
                if self.table.item(fila, 0).checkState() == Qt.Checked]
