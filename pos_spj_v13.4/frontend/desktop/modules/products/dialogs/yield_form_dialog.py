"""YieldProfileFormDialog — alta/edición de la versión DRAFT de un rendimiento (§16).

UI-only: outputs con producto/unidad por catálogo (no UUID a mano), % esperado/
mínimo/máximo y cantidad esperada; panel **en vivo** de total esperado + tolerancia
+ estado (Válido / Fuera de tolerancia) y un **simulador** informativo (entrada de
ejemplo → cantidades por output; no crea inventario). Delega en el presenter →
use cases (validan que la suma caiga dentro de la tolerancia de 100 %).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

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
from frontend.desktop.modules.products.dialogs.recipe_form_dialog import (
    _product_provider,
    _unit_options,
)

_OUTPUT_TYPES = (
    ("MAIN_PRODUCT", "Producto principal"),
    ("CO_PRODUCT", "Coproducto"),
    ("BY_PRODUCT", "Subproducto"),
    ("WASTE", "Merma"),
    ("LOSS", "Pérdida"),
)
_TYPE_ES = dict(_OUTPUT_TYPES)


def _dec(value, default="0") -> Decimal:
    try:
        return Decimal(str(value).strip() or default)
    except (InvalidOperation, AttributeError):
        return Decimal(default)


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
        self.setMinimumSize(620, 540)
        self._outputs: list[dict] = list(self._version.get("outputs", []))

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(str(self._version.get("profile_name") or ""))
        self.tolerance = PercentInput()
        self.tolerance.setValue(float(_dec(self._version.get("tolerance_pct") or 0)))
        self.tolerance.valueChanged.connect(self._refresh_total)
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
            ColumnSpec("Producto", "product"),
            ColumnSpec("Tipo", "tipo"),
            ColumnSpec("% esperado", "pct"),
            ColumnSpec("% mín", "min"),
            ColumnSpec("% máx", "max"),
            ColumnSpec("Unidad", "unit")])
        layout.addWidget(self.table, 1)

        # panel de total en vivo (§16)
        self._total_label = QLabel()
        self._total_label.setObjectName("yieldTotalPanel")
        layout.addWidget(self._total_label)

        # simulador informativo (§16.1)
        sim = QHBoxLayout()
        sim.addWidget(QLabel("Entrada de ejemplo:"))
        self.sim_input = DecimalInput(precision=3, suffix="kg")
        sim.addWidget(self.sim_input)
        self.btn_sim = QPushButton("Simular")
        self.btn_sim.clicked.connect(self._simulate)
        sim.addWidget(self.btn_sim)
        sim.addStretch(1)
        layout.addLayout(sim)
        self.sim_result = QLabel()
        self.sim_result.setWordWrap(True)
        layout.addWidget(self.sim_result)

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

    # ── total en vivo (§16) ────────────────────────────────────────────────────
    def total_expected(self) -> Decimal:
        return sum((_dec(o.get("expected_yield_pct")) for o in self._outputs),
                   Decimal("0"))

    def status(self) -> tuple[str, str]:
        """Devuelve (texto_estado, delta_texto) contra 100 % ± tolerancia."""
        total = self.total_expected()
        tol = _dec(self.tolerance.value())
        diff = total - Decimal("100")
        if abs(diff) <= tol:
            return "Válido", ""
        if diff > 0:
            return "Fuera de tolerancia", f"Exceso: {diff:.2f} %"
        return "Fuera de tolerancia", f"Faltante: {(-diff):.2f} %"

    def _refresh_total(self) -> None:
        total = self.total_expected()
        tol = _dec(self.tolerance.value())
        estado, delta = self.status()
        extra = f" · {delta}" if delta else ""
        self._total_label.setText(
            f"Total esperado: {total:.2f} %  ·  Tolerancia: ±{tol:.2f} %  ·  "
            f"Estado: {estado}{extra}")

    def _refresh_table(self) -> None:
        rows = [[o.get("product_label") or o.get("product_id", ""),
                 _TYPE_ES.get(o.get("output_type"), o.get("output_type", "")),
                 str(o.get("expected_yield_pct", "")),
                 str(o.get("minimum_yield_pct") or ""),
                 str(o.get("maximum_yield_pct") or ""),
                 o.get("unit_label") or o.get("unit_id", "")]
                for o in self._outputs]
        self.table.load_rows(rows, row_ids=[str(i) for i in range(len(self._outputs))])
        self._refresh_total()

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

    def _simulate(self) -> None:
        base = self.sim_input.decimal_value() or Decimal("0")
        if base <= 0 or not self._outputs:
            self.sim_result.setText("Ingresa una entrada de ejemplo y agrega outputs.")
            return
        lines = []
        for o in self._outputs:
            qty = (base * _dec(o.get("expected_yield_pct")) / Decimal("100"))
            label = o.get("product_label") or o.get("product_id", "")
            lines.append(f"{label}: {qty:.3f}")
        self.sim_result.setText("Resultado (informativo, no crea inventario):\n"
                                + "\n".join(lines))

    def _on_save(self) -> None:
        self._error.setText("")
        if not self._outputs:
            self._error.setText("Agrega al menos un output.")
            return
        tolerance = str(_dec(self.tolerance.value()))
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
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._labels: dict = {}
        self.setWindowTitle("Output de rendimiento")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.product = EntitySearchInput(
            provider=_product_provider(presenter, self._labels),
            placeholder="Buscar producto…")
        self.output_type = QComboBox()
        for value, label in _OUTPUT_TYPES:
            self.output_type.addItem(label, value)
        self.pct = PercentInput()
        self.pct_min = PercentInput()
        self.pct_max = PercentInput()
        self.qty = DecimalInput(precision=3, nullable=True)
        self.unit = SearchableComboBox(placeholder="Unidad…")
        self.unit.set_options(_unit_options(presenter))
        form.addRow("Producto *", self.product)
        form.addRow("Tipo *", self.output_type)
        form.addRow("% esperado *", self.pct)
        form.addRow("% mínimo", self.pct_min)
        form.addRow("% máximo", self.pct_max)
        form.addRow("Cantidad esperada", self.qty)
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
        if not self.unit.has_selection():
            self._error.setText("Selecciona una unidad."); return
        if self.pct.value() <= 0:
            self._error.setText("% esperado debe ser mayor a 0."); return
        self.accept()

    def value(self) -> dict:
        pid = self.product.selected_id()
        out = {"product_id": pid, "product_label": self._labels.get(pid, ""),
               "output_type": self.output_type.currentData(),
               "expected_yield_pct": str(self.pct.value()),
               "unit_id": self.unit.current_id(),
               "unit_label": self.unit.currentText()}
        if self.pct_min.value() > 0:
            out["minimum_yield_pct"] = str(self.pct_min.value())
        if self.pct_max.value() > 0:
            out["maximum_yield_pct"] = str(self.pct_max.value())
        qty = self.qty.decimal_value()
        if qty is not None and qty > 0:
            out["expected_quantity"] = str(qty)
        return out
