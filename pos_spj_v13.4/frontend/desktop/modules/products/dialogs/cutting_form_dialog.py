"""CuttingSchemeFormDialog — alta/edición de la versión DRAFT de un despiece (§18).

UI-only: captura nombre, **especie** (por catálogo, no UUID a mano), nivel de corte
y una tabla de outputs (producto/unidad por catálogo, tipo, medida peso/pieza,
cantidad). Delega en el presenter → use cases (validan outputs, duplicados y
auto-contención). En edición sólo cambia los outputs de la versión.
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

from frontend.desktop.components import (
    ColumnSpec,
    DecimalInput,
    EntitySearchInput,
    SearchableComboBox,
    StandardTable,
)
from frontend.desktop.modules.products.dialogs.recipe_form_dialog import (
    _product_provider,
    _unit_options,
)

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
_MEASURE_ES = dict(_MEASURE)


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
        self.setMinimumSize(600, 480)
        self._outputs: list[dict] = list(self._version.get("outputs", []))

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(str(self._version.get("scheme_name") or ""))
        # §18/§5.2: especie por catálogo canónico (guarda species.id, no texto).
        self.species = SearchableComboBox(placeholder="Especie…")
        self.species.set_options([(s["id"], s["label"])
                                  for s in presenter.list_species()])
        if species_id:
            # si la especie preseleccionada no está en el catálogo (inactiva o sin
            # factory), la agregamos para poder conservarla.
            if not self.species.set_current_id(species_id):
                self.species.addItem(species_id, species_id)
                self.species.set_current_id(species_id)
        self.cut_level = QComboBox()
        for value, label in _CUT_LEVELS:
            self.cut_level.addItem(label, value)
        if self._is_edit:
            form.addRow("Versión", QLabel(f"v{self._version.get('version_number', '?')}"))
        else:
            form.addRow("Nombre *", self.name)
            form.addRow("Especie *", self.species)
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
            ColumnSpec("Producto", "product"),
            ColumnSpec("Tipo", "tipo"),
            ColumnSpec("Medida", "medida"),
            ColumnSpec("Cantidad", "quantity"),
            ColumnSpec("Unidad", "unit")])
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
        rows = [[o.get("product_label") or o.get("product_id", ""),
                 _TYPE_ES.get(o.get("output_type"), o.get("output_type", "")),
                 _MEASURE_ES.get(o.get("measure_kind"), o.get("measure_kind", "")),
                 str(o.get("quantity", "")),
                 o.get("unit_label") or o.get("unit_id", "")] for o in self._outputs]
        self.table.load_rows(rows, row_ids=[str(i) for i in range(len(self._outputs))])

    def _add_output(self) -> None:
        dlg = _OutputEditor(self._presenter, parent=self)
        if dlg.exec_():
            self._outputs.append(dlg.value())
            self._refresh_table()

    def _remove_output(self) -> None:
        idx = self.table.selected_row_id()
        if idx is not None and 0 <= int(idx) < len(self._outputs):
            self._outputs.pop(int(idx))
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
            species = self.species.current_id() if self.species.has_selection() else ""
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
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._labels: dict = {}
        self.setWindowTitle("Output de despiece")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.product = EntitySearchInput(
            provider=_product_provider(presenter, self._labels),
            placeholder="Buscar producto…")
        self.output_type = QComboBox()
        for value, label in _OUTPUT_TYPES:
            self.output_type.addItem(label, value)
        self.measure = QComboBox()
        for value, label in _MEASURE:
            self.measure.addItem(label, value)
        self.quantity = DecimalInput(precision=3)
        self.unit = SearchableComboBox(placeholder="Unidad…")
        self.unit.set_options(_unit_options(presenter))
        form.addRow("Producto *", self.product)
        form.addRow("Tipo *", self.output_type)
        form.addRow("Medida *", self.measure)
        form.addRow("Cantidad *", self.quantity)
        form.addRow("Unidad *", self.unit)
        layout.addLayout(form)
        self._error = QLabel(); self._error.setObjectName("textDanger")
        layout.addWidget(self._error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if not self.product.selected_id():
            self._error.setText("Selecciona un producto."); return
        if self.quantity.decimal_value() is None or self.quantity.decimal_value() <= 0:
            self._error.setText("Cantidad debe ser mayor a 0."); return
        if not self.unit.has_selection():
            self._error.setText("Selecciona una unidad."); return
        self.accept()

    def value(self) -> dict:
        pid = self.product.selected_id()
        return {"product_id": pid, "product_label": self._labels.get(pid, ""),
                "output_type": self.output_type.currentData(),
                "measure_kind": self.measure.currentData(),
                "quantity": str(self.quantity.decimal_value()),
                "unit_id": self.unit.current_id(),
                "unit_label": self.unit.currentText()}
