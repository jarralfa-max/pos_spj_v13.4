"""YieldProfileFormDialog — alta/edición de la versión DRAFT de un rendimiento.

UI-only: captura nombre, tolerancia (%) y una tabla de outputs (producto, tipo,
% esperado, unidad). Delega en el presenter → use cases (validan que la suma de
rendimientos caiga dentro de la tolerancia de 100 %). En edición sólo cambia los
outputs/tolerancia de la versión.
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

_OUTPUT_TYPES = (
    ("MAIN_PRODUCT", "Producto principal"),
    ("CO_PRODUCT", "Coproducto"),
    ("BY_PRODUCT", "Subproducto"),
    ("WASTE", "Merma"),
    ("LOSS", "Pérdida"),
)
_TYPE_ES = dict(_OUTPUT_TYPES)


class YieldProfileFormDialog(QDialog):
    def __init__(self, presenter, *, input_product_id: str, version=None,
                 parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._input_product_id = input_product_id
        self._version = version or {}
        self._version_id = self._version.get("id")
        self._is_edit = self._version_id is not None
        self.setObjectName("yieldFormDialog")
        self.setWindowTitle("Editar rendimiento" if self._is_edit
                            else "Nuevo rendimiento")
        self.setMinimumSize(560, 440)
        self._outputs: list[dict] = list(self._version.get("outputs", []))

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(str(self._version.get("profile_name") or ""))
        self.tolerance = QLineEdit(str(self._version.get("tolerance_pct") or "0"))
        if self._is_edit:
            self.name.setEnabled(False)
            form.addRow("Versión", QLabel(f"v{self._version.get('version_number', '?')}"))
        else:
            form.addRow("Nombre *", self.name)
        form.addRow("Tolerancia % *", self.tolerance)
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
            ColumnSpec("% esperado", "expected_yield_pct"),
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
                 str(o.get("expected_yield_pct", "")), o.get("unit_id", "")]
                for o in self._outputs]
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
        tolerance = self.tolerance.text().strip() or "0"
        if self._is_edit:
            ok, message = self._presenter.update_yield_version(
                version_id=self._version_id, tolerance_pct=tolerance,
                outputs=self._outputs)
        else:
            name = self.name.text().strip()
            if not name:
                self._error.setText("El nombre es obligatorio.")
                return
            ok, message = self._presenter.create_yield_profile(
                input_product_id=self._input_product_id, name=name,
                tolerance_pct=tolerance, outputs=self._outputs)
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            QMessageBox.warning(self, "No se pudo guardar", message)


class _OutputEditor(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Output de rendimiento")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.product = QLineEdit()
        self.output_type = QComboBox()
        for value, label in _OUTPUT_TYPES:
            self.output_type.addItem(label, value)
        self.pct = QLineEdit()
        self.unit = QLineEdit()
        form.addRow("Producto (id) *", self.product)
        form.addRow("Tipo *", self.output_type)
        form.addRow("% esperado *", self.pct)
        form.addRow("Unidad (id) *", self.unit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if self.product.text().strip() and self.pct.text().strip() \
                and self.unit.text().strip():
            self.accept()

    def value(self) -> dict:
        return {"product_id": self.product.text().strip(),
                "output_type": self.output_type.currentData(),
                "expected_yield_pct": self.pct.text().strip(),
                "unit_id": self.unit.text().strip()}
