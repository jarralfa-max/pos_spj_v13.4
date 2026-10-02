"""PurchaseUnitsDialog — presentaciones de compra de un producto.

Productos es la ÚNICA fuente de las unidades con que Compras captura una línea:
la unidad base (la de inventario) y cada presentación (caja, costal, paquete…)
con su equivalencia en unidades base. Compras sólo elige entre éstas; ya no deja
escribir un factor ni marcar "por peso".

UI-only: toda mutación pasa por el presenter → use cases (autorización +
detección de ciclos + bitácora). Una presentación nunca se borra, se retira: las
compras registradas conservan su propio factor.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from frontend.desktop.components import (
    ColumnSpec,
    DecimalInput,
    SearchableComboBox,
    StandardCheckBox,
    StandardTable,
)


def _plain(value: str) -> str:
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, ValueError):
        return str(value)


class PurchaseUnitsDialog(QDialog):
    def __init__(self, presenter, *, product_id: str, product_name: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._product_id = product_id
        self.setObjectName("purchaseUnitsDialog")
        self.setWindowTitle(f"Unidades de compra de «{product_name}»")
        self.setMinimumSize(620, 440)
        can_manage = bool(getattr(presenter, "can_manage_purchase_units", False))

        layout = QVBoxLayout(self)
        self.base_label = QLabel("", self)
        self.base_label.setWordWrap(True)
        layout.addWidget(self.base_label)

        self.table = StandardTable(columns=[
            ColumnSpec("Unidad", "unit"),
            ColumnSpec("Equivale a", "factor"),
            ColumnSpec("Alcance", "scope"),
            ColumnSpec("Recepción", "receipt"),
        ])
        self.table.itemSelectionChanged.connect(self._sync_buttons)
        layout.addWidget(self.table, 1)

        layout.addWidget(QLabel("Nueva presentación", self))
        form = QHBoxLayout()
        form.addWidget(QLabel("1", self))
        self.unit = SearchableComboBox(self, placeholder="Unidad (caja, costal…)")
        form.addWidget(self.unit, 2)
        form.addWidget(QLabel("=", self))
        self.factor = DecimalInput(self, precision=6, minimum="0")
        form.addWidget(self.factor, 1)
        self.base_suffix = QLabel("", self)
        form.addWidget(self.base_suffix)
        # §27: lo decide la presentación, no Compras.
        self.fractional = StandardCheckBox("Se puede recibir en fracción", self)
        self.fractional.setChecked(True)
        form.addWidget(self.fractional)
        self.btn_add = QPushButton("Agregar")
        self.btn_add.setEnabled(can_manage)
        self.btn_add.clicked.connect(self._add)
        form.addWidget(self.btn_add)
        layout.addLayout(form)

        bar = QHBoxLayout()
        self.btn_fraction = QPushButton("Cambiar recepción en fracción")
        self.btn_fraction.setEnabled(False)
        self.btn_fraction.clicked.connect(self._toggle_fraction)
        bar.addWidget(self.btn_fraction)
        self.btn_retire = QPushButton("Retirar presentación")
        self.btn_retire.setEnabled(False)
        self.btn_retire.clicked.connect(self._retire)
        bar.addWidget(self.btn_retire)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.message = QLabel("", self)
        self.message.setWordWrap(True)
        self.message.setProperty("role", "banner")
        self.message.hide()
        layout.addWidget(self.message)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._can_manage = can_manage
        self._retirable: dict[str, str] = {}
        self._fractional: dict[str, bool] = {}
        self.refresh()

    def refresh(self) -> None:
        profile = self._presenter.purchase_unit_profile(self._product_id)
        if profile is None or not profile.base_unit_code:
            self.base_label.setText("Este producto no tiene unidad base. Edítalo y asigna una "
                                    "antes de configurar presentaciones de compra.")
            self.table.load_rows([], row_ids=[])
            self.btn_add.setEnabled(False)
            return
        base = profile.base_unit_code
        self.base_label.setText(
            f"Unidad base (inventario y costo): {profile.base_unit_name} ({base}). "
            "Compras sólo puede capturar en estas unidades.")
        self.base_suffix.setText(base)
        rows, ids = [], []
        self._retirable = {}
        self._fractional = {}
        for index, unit in enumerate(profile.purchase_units):
            row_id = unit.conversion_id or f"base-{index}"
            rows.append([f"{unit.name} ({unit.code})",
                         "Unidad base" if unit.is_base else f"{_plain(unit.factor_to_base)} {base}",
                         "—" if unit.is_base else
                         ("Este producto" if unit.product_specific else "Todas (global)"),
                         "Admite fracción" if unit.is_base or getattr(
                             unit, "fractional_receipt", True) else "Sólo completas"])
            ids.append(row_id)
            if unit.product_specific and unit.conversion_id:
                self._retirable[row_id] = unit.conversion_id
                self._fractional[row_id] = bool(getattr(unit, "fractional_receipt", True))
        self.table.load_rows(rows, row_ids=ids)
        self.unit.set_options(self._presenter.purchase_unit_choices(self._product_id))
        self.btn_add.setEnabled(self._can_manage)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        selected = self.table.selected_row_id()
        self.btn_retire.setEnabled(self._can_manage and selected in self._retirable)
        self.btn_fraction.setEnabled(self._can_manage and selected in self._retirable)

    def _add(self) -> None:
        unit_id = self.unit.current_id()
        factor = self.factor.decimal_value()
        if not unit_id:
            self._show(False, "Elige la unidad de la presentación.")
            return
        if factor is None or factor <= 0:
            self._show(False, "La equivalencia debe ser mayor a cero.")
            return
        ok, message = self._presenter.add_purchase_unit(
            self._product_id, unit_id, str(factor),
            fractional_receipt=self.fractional.isChecked())
        self._show(ok, message)
        if ok:
            self.factor.set_decimal(None)
            self.refresh()

    def _toggle_fraction(self) -> None:
        row_id = self.table.selected_row_id() or ""
        conversion_id = self._retirable.get(row_id)
        if not conversion_id:
            return
        ok, message = self._presenter.set_purchase_unit_fractional(
            conversion_id, not self._fractional.get(row_id, True))
        self._show(ok, message)
        if ok:
            self.refresh()

    def _retire(self) -> None:
        conversion_id = self._retirable.get(self.table.selected_row_id() or "")
        if not conversion_id:
            return
        ok, message = self._presenter.retire_purchase_unit(conversion_id)
        self._show(ok, message)
        if ok:
            self.refresh()

    def _show(self, ok: bool, text: str) -> None:
        self.message.setProperty("state", "success" if ok else "error")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setText(text)
        self.message.setVisible(bool(text))
