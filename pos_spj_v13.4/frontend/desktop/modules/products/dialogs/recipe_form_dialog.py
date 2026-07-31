"""RecipeFormDialog — alta/edición de la versión DRAFT de una receta (recetas UI).

UI-only: captura nombre, tipo, una tabla de **componentes** (entrada) y una tabla de
**outputs** (§15: MAIN/CO/BY-product, merma, pérdida). Producto y unidad se eligen
por catálogo canónico (EntitySearchInput / SearchableComboBox), nunca por UUID a
mano; cantidades con DecimalInput y porcentaje con PercentInput. Delega en el
presenter → use cases canónicos (validan Decimal, duplicados y ciclos).
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
    PercentInput,
    SearchableComboBox,
    StandardTable,
)
from frontend.desktop.components.search_selector import SearchOption

_RECIPE_TYPES = (
    ("PRODUCTION_BOM", "BOM de producción"),
    ("SALES_EXPLOSION", "Explosión de venta"),
    ("PROCESSING_RECIPE", "Receta de proceso"),
    ("PACKAGING_BOM", "BOM de empaque"),
    ("DISASSEMBLY", "Desensamble"),
    ("FORMULA", "Fórmula"),
    ("GRINDING", "Molienda"),
    ("MIXING", "Mezcla"),
    ("MARINATION", "Marinado"),
)

_OUTPUT_TYPES = (
    ("MAIN_PRODUCT", "Producto principal"),
    ("CO_PRODUCT", "Co-producto"),
    ("BY_PRODUCT", "Subproducto"),
    ("WASTE", "Merma"),
    ("LOSS", "Pérdida"),
)


def _product_provider(presenter, label_cache: dict):
    """Provider para EntitySearchInput que además cachea id→label (para mostrar el
    nombre en la tabla sin volver a consultar)."""
    def provider(query: str):
        rows = presenter.search_products_for_assignment(query=query)
        opts = [SearchOption(id=r["id"], label=r["name"], subtitle=r.get("code") or "")
                for r in rows]
        for o in opts:
            label_cache[o.id] = o.label
        return opts
    return provider


def _unit_options(presenter) -> list[tuple]:
    return [(u["id"], f'{u["code"]} — {u["name"]}') for u in presenter.list_units()]


class RecipeFormDialog(QDialog):
    def __init__(self, presenter, *, product_id: str, version=None,
                 parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._product_id = product_id
        self._version = version or {}
        self._version_id = self._version.get("id")
        self._is_edit = self._version_id is not None
        self.setObjectName("recipeFormDialog")
        self.setWindowTitle("Editar componentes" if self._is_edit else "Nueva receta")
        self.setMinimumSize(560, 520)
        self._components: list[dict] = list(self._version.get("components", []))
        self._outputs: list[dict] = list(self._version.get("outputs", []))

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(str(self._version.get("recipe_name") or ""))
        self.recipe_type = QComboBox()
        for value, label in _RECIPE_TYPES:
            self.recipe_type.addItem(label, value)
        if self._is_edit:
            self.name.setEnabled(False)
            self.recipe_type.setEnabled(False)
            form.addRow("Versión", QLabel(f"v{self._version.get('version_number', '?')}"))
        else:
            form.addRow("Nombre *", self.name)
            form.addRow("Tipo *", self.recipe_type)
        layout.addLayout(form)

        # ── componentes (entrada) ────────────────────────────────────────────
        layout.addWidget(QLabel("Componentes (entrada)"))
        ctools = QHBoxLayout()
        self.btn_add = QPushButton("Agregar componente")
        self.btn_remove = QPushButton("Quitar")
        ctools.addWidget(self.btn_add)
        ctools.addWidget(self.btn_remove)
        ctools.addStretch(1)
        layout.addLayout(ctools)
        self.btn_add.clicked.connect(self._add_component)
        self.btn_remove.clicked.connect(self._remove_component)
        self.table = StandardTable(columns=[
            ColumnSpec("Producto", "product"),
            ColumnSpec("Cantidad", "quantity"),
            ColumnSpec("Unidad", "unit")])
        layout.addWidget(self.table, 1)

        # ── outputs (salida) — §15 ───────────────────────────────────────────
        layout.addWidget(QLabel("Outputs (salida)"))
        otools = QHBoxLayout()
        self.btn_add_out = QPushButton("Agregar output")
        self.btn_remove_out = QPushButton("Quitar")
        otools.addWidget(self.btn_add_out)
        otools.addWidget(self.btn_remove_out)
        otools.addStretch(1)
        layout.addLayout(otools)
        self.btn_add_out.clicked.connect(self._add_output)
        self.btn_remove_out.clicked.connect(self._remove_output)
        self.outputs_table = StandardTable(columns=[
            ColumnSpec("Producto", "product"),
            ColumnSpec("Tipo", "tipo"),
            ColumnSpec("Cantidad", "quantity"),
            ColumnSpec("% esperado", "pct")])
        layout.addWidget(self.outputs_table, 1)

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
        self._refresh_tables()

    # ── tablas ────────────────────────────────────────────────────────────────
    def _refresh_tables(self) -> None:
        self.table.load_rows(
            [[c.get("product_label") or c.get("component_product_id", ""),
              str(c.get("quantity", "")), c.get("unit_label") or c.get("unit_id", "")]
             for c in self._components],
            row_ids=[str(i) for i in range(len(self._components))])
        types = dict(_OUTPUT_TYPES)
        self.outputs_table.load_rows(
            [[o.get("product_label") or o.get("product_id", ""),
              types.get(o.get("output_type"), o.get("output_type", "")),
              str(o.get("quantity", "")), str(o.get("expected_yield_pct") or "")]
             for o in self._outputs],
            row_ids=[str(i) for i in range(len(self._outputs))])

    def _add_component(self) -> None:
        dlg = _ComponentEditor(self._presenter, parent=self)
        if dlg.exec_():
            self._components.append(dlg.value())
            self._refresh_tables()

    def _remove_component(self) -> None:
        idx = self.table.selected_row_id()
        if idx is not None and 0 <= int(idx) < len(self._components):
            self._components.pop(int(idx))
            self._refresh_tables()

    def _add_output(self) -> None:
        dlg = _OutputEditor(self._presenter, parent=self)
        if dlg.exec_():
            self._outputs.append(dlg.value())
            self._refresh_tables()

    def _remove_output(self) -> None:
        idx = self.outputs_table.selected_row_id()
        if idx is not None and 0 <= int(idx) < len(self._outputs):
            self._outputs.pop(int(idx))
            self._refresh_tables()

    def _on_save(self) -> None:
        self._error.setText("")
        if not self._components:
            self._error.setText("Agrega al menos un componente.")
            return
        if self._is_edit:
            ok, message = self._presenter.update_draft_version(
                version_id=self._version_id, components=self._components,
                outputs=self._outputs)
        else:
            name = self.name.text().strip()
            if not name:
                self._error.setText("El nombre es obligatorio.")
                return
            ok, message = self._presenter.create_recipe(
                product_id=self._product_id, recipe_type=self.recipe_type.currentData(),
                name=name, components=self._components, outputs=self._outputs)
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            QMessageBox.warning(self, "No se pudo guardar", message)


class _ComponentEditor(QDialog):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self.setWindowTitle("Componente")
        self.setMinimumWidth(420)
        self._labels: dict = {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.product = EntitySearchInput(
            provider=_product_provider(presenter, self._labels),
            placeholder="Buscar producto…")
        self.quantity = DecimalInput(precision=3)
        self.unit = SearchableComboBox(placeholder="Unidad…")
        self.unit.set_options(_unit_options(presenter))
        form.addRow("Producto *", self.product)
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
        return {"component_product_id": pid,
                "product_label": self._labels.get(pid, ""),
                "quantity": str(self.quantity.decimal_value()),
                "unit_id": self.unit.current_id(),
                "unit_label": self.unit.currentText()}


class _OutputEditor(QDialog):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self.setWindowTitle("Output")
        self.setMinimumWidth(420)
        self._labels: dict = {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.product = EntitySearchInput(
            provider=_product_provider(presenter, self._labels),
            placeholder="Buscar producto…")
        self.output_type = QComboBox()
        for value, label in _OUTPUT_TYPES:
            self.output_type.addItem(label, value)
        self.quantity = DecimalInput(precision=3)
        self.unit = SearchableComboBox(placeholder="Unidad…")
        self.unit.set_options(_unit_options(presenter))
        self.pct = PercentInput()
        form.addRow("Producto *", self.product)
        form.addRow("Tipo *", self.output_type)
        form.addRow("Cantidad esperada *", self.quantity)
        form.addRow("Unidad *", self.unit)
        form.addRow("% esperado", self.pct)
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
        pct = self.pct.value()
        pid = self.product.selected_id()
        return {"product_id": pid,
                "product_label": self._labels.get(pid, ""),
                "output_type": self.output_type.currentData(),
                "quantity": str(self.quantity.decimal_value()),
                "unit_id": self.unit.current_id(),
                "unit_label": self.unit.currentText(),
                "expected_yield_pct": str(pct) if pct else None}
