"""CuttingSchemeFormDialog — alta/edición de la versión DRAFT de un despiece.

UI-only: captura nombre, especie, nivel de corte y una tabla de outputs (producto,
tipo, medida, cantidad, unidad). Delega en el presenter → use cases (validan outputs,
duplicados y auto-contención). En edición sólo cambia los outputs de la versión.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from frontend.desktop.components import ColumnSpec, StandardTable

_CUT_LEVELS = (
    ("CARCASS", "Canal"), ("PRIMARY", "Corte primario"),
    ("SECONDARY", "Corte secundario"), ("PORTION", "Porcionado"),
)
_OUTPUT_TYPES = (
    ("MAIN_PRODUCT", "Producto principal"), ("CO_PRODUCT", "Coproducto"),
    ("BY_PRODUCT", "Subproducto"), ("WASTE", "Merma"), ("LOSS", "Pérdida"),
)
_MEASURE = (("BY_WEIGHT", "Por peso"), ("BY_PIECE", "Por pieza"))
_TYPE_ES = dict(_OUTPUT_TYPES)


class CuttingSchemeFormDialog(QDialog):
    def __init__(self, presenter, *, input_product_id: str, species_id: str = "",
                 version=None, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._input_product_id = input_product_id
        self._version = version or {}
        self._version_id = self._version.get("id")
        self._is_edit = self._version_id is not None
        self.setObjectName("cuttingFormDialog")
        self.setWindowTitle("Editar despiece" if self._is_edit else "Nuevo despiece")
        self.setMinimumSize(600, 460)
        self._outputs: list[dict] = list(self._version.get("outputs", []))

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(str(self._version.get("scheme_name") or ""))
        self.species = QLineEdit(species_id)
        self.cut_level = QComboBox()
        for value, label in _CUT_LEVELS:
            self.cut_level.addItem(label, value)
        if self._is_edit:
            form.addRow("Versión", QLabel(f"v{self._version.get('version_number', '?')}"))
        else:
            form.addRow("Nombre *", self.name)
            form.addRow("Especie (id) *", self.species)
            form.addRow("Nivel de corte", self.cut_level)
        layout.addLayout(form)

        toolbar = QHBoxLayout()
        self.btn_add = QPushButton("Agregar output")
        self.btn_remove = QPushButton("Quitar")
        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_remove)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.btn_add.clicked.connect(self._add_output)
        self.btn_remove.clicked.connect(self._remove_output)

        self.table = StandardTable(columns=[
            ColumnSpec("Producto (id)", "product_id"),
            ColumnSpec("Tipo", "output_type"),
            ColumnSpec("Medida", "measure_kind"),
            ColumnSpec("Cantidad", "quantity"),
            ColumnSpec("Unidad (id)", "unit_id"),
        ])
        layout.addWidget(self.table, 1)

        self._error = QLabel()
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_table()

    def _refresh_table(self) -> None:
        rows = [[o.get("product_id", ""),
                 _TYPE_ES.get(o.get("output_type"), o.get("output_type", "")),
                 o.get("measure_kind", ""), str(o.get("quantity", "")),
                 o.get("unit_id", "")] for o in self._outputs]
        self.table.load_rows(rows, row_ids=[str(i) for i in range(len(self._outputs))])

    def _add_output(self) -> None:
        dlg = _OutputEditor(parent=self)
        if dlg.exec_():
            self._outputs.append(dlg.value())
            self._refresh_table()

    def _remove_output(self) -> None:
        idx = self.table.selected_row_id()
        if idx is None:
            return
        i = int(idx)
        if 0 <= i < len(self._outputs):
            self._outputs.pop(i)
            self._refresh_table()

    def _on_save(self) -> None:
        self._error.setText("")
        if not self._outputs:
            self._error.setText("Agrega al menos un output.")
            return
        if self._is_edit:
            ok, message = self._presenter.update_cutting_version(
                version_id=self._version_id, outputs=self._outputs)
        else:
            name = self.name.text().strip()
            species = self.species.text().strip()
            if not name or not species:
                self._error.setText("Nombre y Especie son obligatorios.")
                return
            ok, message = self._presenter.create_cutting_scheme(
                input_product_id=self._input_product_id, species_id=species,
                name=name, cut_level=self.cut_level.currentData(),
                outputs=self._outputs)
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            QMessageBox.warning(self, "No se pudo guardar", message)


class _OutputEditor(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Output de despiece")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.product = QLineEdit()
        self.output_type = QComboBox()
        for value, label in _OUTPUT_TYPES:
            self.output_type.addItem(label, value)
        self.measure = QComboBox()
        for value, label in _MEASURE:
            self.measure.addItem(label, value)
        self.quantity = QLineEdit()
        self.unit = QLineEdit()
        form.addRow("Producto (id) *", self.product)
        form.addRow("Tipo *", self.output_type)
        form.addRow("Medida *", self.measure)
        form.addRow("Cantidad *", self.quantity)
        form.addRow("Unidad (id) *", self.unit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if self.product.text().strip() and self.quantity.text().strip() \
                and self.unit.text().strip():
            self.accept()

    def value(self) -> dict:
        return {"product_id": self.product.text().strip(),
                "output_type": self.output_type.currentData(),
                "measure_kind": self.measure.currentData(),
                "quantity": self.quantity.text().strip(),
                "unit_id": self.unit.text().strip()}
