"""BundleFormDialog — alta/edición de la versión DRAFT de un combo/kit (§28).

UI-only: captura nombre, tipo de combo y una tabla de componentes (producto,
cantidad, unidad, opcional/sustituible). Delega en el presenter → use cases (validan
componentes, duplicados y ciclos). En edición sólo cambia los componentes.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox,
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

_BUNDLE_TYPES = (
    ("FIXED_COMBO", "Combo fijo"),
    ("CONFIGURABLE_COMBO", "Combo configurable"),
    ("VIRTUAL_BUNDLE", "Combo virtual (se descompone al vender)"),
    ("STOCKED_KIT", "Kit con stock propio"),
    ("MIX_AND_MATCH", "Arma tu combo"),
    ("ASSORTED_PACKAGE", "Paquete surtido"),
    ("GIFT_SET", "Set de regalo"),
    ("MEAT_BOX", "Caja cárnica"),
)


class BundleFormDialog(QDialog):
    def __init__(self, presenter, *, product_id: str, version=None,
                 parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._product_id = product_id
        self._version = version or {}
        self._version_id = self._version.get("id")
        self._is_edit = self._version_id is not None
        self.setObjectName("bundleFormDialog")
        self.setWindowTitle("Editar componentes" if self._is_edit else "Nuevo combo")
        self.setMinimumSize(560, 440)
        self._components: list[dict] = list(self._version.get("components", []))

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(str(self._version.get("bundle_name") or ""))
        self.bundle_type = QComboBox()
        for value, label in _BUNDLE_TYPES:
            self.bundle_type.addItem(label, value)
        if self._is_edit:
            form.addRow("Versión", QLabel(f"v{self._version.get('version_number', '?')}"))
        else:
            form.addRow("Nombre *", self.name)
            form.addRow("Tipo *", self.bundle_type)
        layout.addLayout(form)

        toolbar = QHBoxLayout()
        self.btn_add = QPushButton("Agregar componente")
        self.btn_remove = QPushButton("Quitar")
        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_remove)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.btn_add.clicked.connect(self._add_component)
        self.btn_remove.clicked.connect(self._remove_component)

        self.table = StandardTable(columns=[
            ColumnSpec("Producto (id)", "component_product_id"),
            ColumnSpec("Cantidad", "quantity"),
            ColumnSpec("Unidad (id)", "unit_id"),
            ColumnSpec("Opcional", "optional"),
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
        rows = [[c.get("component_product_id", ""), str(c.get("quantity", "")),
                 c.get("unit_id", ""), "Sí" if c.get("optional") else ""]
                for c in self._components]
        self.table.load_rows(rows, row_ids=[str(i) for i in range(len(self._components))])

    def _add_component(self) -> None:
        dlg = _ComponentEditor(parent=self)
        if dlg.exec_():
            self._components.append(dlg.value())
            self._refresh_table()

    def _remove_component(self) -> None:
        idx = self.table.selected_row_id()
        if idx is None:
            return
        i = int(idx)
        if 0 <= i < len(self._components):
            self._components.pop(i)
            self._refresh_table()

    def _on_save(self) -> None:
        self._error.setText("")
        if not self._components:
            self._error.setText("Agrega al menos un componente.")
            return
        if self._is_edit:
            ok, message = self._presenter.update_bundle_version(
                version_id=self._version_id, components=self._components)
        else:
            name = self.name.text().strip()
            if not name:
                self._error.setText("El nombre es obligatorio.")
                return
            ok, message = self._presenter.create_bundle(
                product_id=self._product_id, bundle_type=self.bundle_type.currentData(),
                name=name, components=self._components)
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            QMessageBox.warning(self, "No se pudo guardar", message)


class _ComponentEditor(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Componente del combo")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.product = QLineEdit()
        self.quantity = QLineEdit()
        self.unit = QLineEdit()
        self.optional = QCheckBox("Opcional")
        self.substitutable = QCheckBox("Sustituible")
        form.addRow("Producto (id) *", self.product)
        form.addRow("Cantidad *", self.quantity)
        form.addRow("Unidad (id) *", self.unit)
        form.addRow("", self.optional)
        form.addRow("", self.substitutable)
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
        return {"component_product_id": self.product.text().strip(),
                "quantity": self.quantity.text().strip(),
                "unit_id": self.unit.text().strip(),
                "optional": self.optional.isChecked(),
                "substitutable": self.substitutable.isChecked()}
