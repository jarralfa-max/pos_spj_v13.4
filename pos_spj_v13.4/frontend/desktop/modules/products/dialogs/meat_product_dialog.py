"""MeatProductDialog — clasificación cárnica y peso variable de UN producto (§11-12).

Pestaña «Clasificación»: categoría cárnica, región anatómica y corte, filtrados
por la especie del producto (la especie se edita en la ficha). Cambiar una
clasificación existente pide motivo (§39). Pestaña «Peso variable»: unidad
nominal (pieza) y de peso (kg), rango, promedio, tolerancia y base de precio.
UI only: todo pasa por el presenter de clasificación cárnica.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components.buttons import create_primary_button
from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.tabs import Tabs
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.modules.products.meat_classification_presenter import (
    CUT_LEVEL_ES,
    MEAT_CATEGORY_ES,
    PRICE_BASIS_ES,
)
from frontend.desktop.themes.tokens import DialogMetrics


def _dec(value) -> str | None:
    return None if value is None else str(value)


class MeatProductDialog(StandardDialog):
    def __init__(self, meat_presenter, *, product_id: str, product_name: str,
                 parent=None) -> None:
        super().__init__(parent, title=f"Clasificación cárnica y peso variable de «{product_name}»",
                         width=DialogMetrics.WIDTH_LG)
        self.setObjectName("meatProductDialog")
        self.setMinimumSize(680, 520)
        self._m = meat_presenter
        self._product_id = product_id
        self._info = self._m.product_classification(product_id)
        self._regions: list[dict] = []
        self._cuts: list[dict] = []

        layout = self.content_layout()
        self.tabs = Tabs(self)
        self.tabs.addTab(self._classification_tab(), "Clasificación")
        self.tabs.addTab(self._catch_weight_tab(), "Peso variable")
        layout.addWidget(self.tabs, 1)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setProperty("role", "banner")
        self.message.hide()
        layout.addWidget(self.message)
        close = QDialogButtonBox(QDialogButtonBox.Close, self)
        close.button(QDialogButtonBox.Close).setText("Cerrar")
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self._load()

    # ── pestañas ──────────────────────────────────────────────────────────
    def _classification_tab(self) -> QWidget:
        tab = QWidget()
        box = QVBoxLayout(tab)
        self.species_label = QLabel("")
        self.species_label.setProperty("role", "muted")
        self.species_label.setWordWrap(True)
        box.addWidget(self.species_label)
        form = QFormLayout()
        self.category = QComboBox()
        self.category.addItem("(Sin categoría)", "")
        for key, label in MEAT_CATEGORY_ES.items():
            self.category.addItem(label, key)
        self.region = QComboBox()
        self.region.currentIndexChanged.connect(lambda _i: self._fill_cuts())
        self.cut = QComboBox()
        self.reason = StandardLineEdit(placeholder="Obligatorio si ya estaba clasificado")
        form.addRow("Categoría cárnica", self.category)
        form.addRow("Región anatómica", self.region)
        form.addRow("Corte", self.cut)
        form.addRow("Motivo del cambio", self.reason)
        box.addLayout(form)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_classify = create_primary_button(self, "Guardar clasificación")
        self.btn_classify.clicked.connect(self._save_classification)
        row.addWidget(self.btn_classify)
        box.addLayout(row)
        box.addStretch(1)
        return tab

    def _catch_weight_tab(self) -> QWidget:
        tab = QWidget()
        box = QVBoxLayout(tab)
        hint = QLabel("Para productos que se cuentan por pieza pero se venden o compran "
                      "por su peso real (pollo entero, piezas de res…).")
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        box.addWidget(hint)
        self.cw_enabled = QCheckBox("Maneja peso variable")
        box.addWidget(self.cw_enabled)
        form = QFormLayout()
        self.nominal_unit = QComboBox()
        self.weight_unit = QComboBox()
        self._unit_code: dict[str, str] = {}
        for unit in self._m.unit_options():
            label = f"{unit['code']} — {unit['name']}"
            self._unit_code[unit["id"]] = (unit["code"] or "").upper()
            self.nominal_unit.addItem(label, unit["id"])
            if unit.get("dimension") == "WEIGHT":
                self.weight_unit.addItem(label, unit["id"])
        self.min_weight = DecimalInput(precision=3, minimum="0", nullable=True)
        self.max_weight = DecimalInput(precision=3, minimum="0", nullable=True)
        self.avg_weight = DecimalInput(precision=3, minimum="0", nullable=True)
        self.tolerance = DecimalInput(precision=2, minimum="0", maximum="100")
        self.price_basis = QComboBox()
        for key, label in PRICE_BASIS_ES.items():
            self.price_basis.addItem(label, key)
        self.label_required = QCheckBox("Requiere etiqueta con peso")
        self.scale_barcode = QCheckBox("Usa código de báscula")
        for label, widget in (("Unidad nominal (conteo)", self.nominal_unit),
                              ("Unidad de peso", self.weight_unit),
                              ("Peso mínimo", self.min_weight),
                              ("Peso máximo", self.max_weight),
                              ("Peso promedio", self.avg_weight),
                              ("Tolerancia (%)", self.tolerance),
                              ("Base de precio", self.price_basis),
                              ("", self.label_required), ("", self.scale_barcode)):
            form.addRow(label, widget)
        box.addLayout(form)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_catch_weight = create_primary_button(self, "Guardar peso variable")
        self.btn_catch_weight.clicked.connect(self._save_catch_weight)
        row.addWidget(self.btn_catch_weight)
        box.addLayout(row)
        box.addStretch(1)
        return tab

    # ── carga ─────────────────────────────────────────────────────────────
    def _load(self) -> None:
        info = self._info or {}
        species_id = info.get("species_id")
        if species_id:
            self.species_label.setText(f"Especie: {info.get('species_name') or species_id}. "
                                       "La especie se cambia en la ficha del producto.")
            self._regions = [r for r in self._m.regions(species_id) if r.get("active")]
            self._cuts = [c for c in self._m.cuts(species_id) if c.get("status") == "ACTIVE"]
        else:
            self.species_label.setText("Este producto no tiene especie: asígnala en la ficha "
                                       "(sólo los productos cárnicos se clasifican).")
        self.region.blockSignals(True)
        self.region.clear()
        self.region.addItem("(Sin región)", "")
        for r in self._regions:
            self.region.addItem(r["name"], r["id"])
        self.region.setCurrentIndex(max(0, self.region.findData(
            info.get("anatomical_region_id") or "")))
        self.region.blockSignals(False)
        self._fill_cuts(select=info.get("cut_classification_id"))
        self.category.setCurrentIndex(max(0, self.category.findData(
            info.get("meat_category") or "")))
        can_classify = bool(species_id) and self._m.can_classify_products
        for widget in (self.category, self.region, self.cut, self.reason, self.btn_classify):
            widget.setEnabled(can_classify)

        cw = self._m.catch_weight(self._product_id) or {}
        if not cw:  # propuesta habitual: se cuenta por pieza y se pesa en kg
            self._select_code(self.nominal_unit, ("PZA", "PZ", "PIEZA", "PIE"))
            self._select_code(self.weight_unit, ("KG",))
        self.cw_enabled.setChecked(bool(cw.get("enabled")))
        for combo, key in ((self.nominal_unit, "nominal_unit_id"),
                           (self.weight_unit, "weight_unit_id")):
            if cw.get(key):
                combo.setCurrentIndex(max(0, combo.findData(cw[key])))
        for widget, key in ((self.min_weight, "minimum_weight"),
                            (self.max_weight, "maximum_weight"),
                            (self.avg_weight, "average_weight"),
                            (self.tolerance, "tolerance_pct")):
            widget.set_decimal(cw.get(key))
        self.price_basis.setCurrentIndex(max(0, self.price_basis.findData(
            cw.get("price_basis") or "PER_KILOGRAM")))
        self.label_required.setChecked(bool(cw.get("label_required", 1)))
        self.scale_barcode.setChecked(bool(cw.get("scale_barcode_enabled")))
        can_cw = self._m.can_manage_catch_weight
        for widget in (self.cw_enabled, self.nominal_unit, self.weight_unit, self.min_weight,
                       self.max_weight, self.avg_weight, self.tolerance, self.price_basis,
                       self.label_required, self.scale_barcode, self.btn_catch_weight):
            widget.setEnabled(can_cw)

    def _select_code(self, combo: QComboBox, codes: tuple[str, ...]) -> None:
        for i in range(combo.count()):
            if self._unit_code.get(combo.itemData(i)) in codes:
                combo.setCurrentIndex(i)
                return

    def _fill_cuts(self, select: str | None = None) -> None:
        region_id = self.region.currentData()
        current = select or self.cut.currentData()
        self.cut.clear()
        self.cut.addItem("(Sin corte)", "")
        for c in self._cuts:
            if region_id and c.get("anatomical_region_id") != region_id:
                continue
            level = CUT_LEVEL_ES.get(c["cut_level"], c["cut_level"])
            self.cut.addItem(f"{c['name']} · {level}", c["id"])
        self.cut.setCurrentIndex(max(0, self.cut.findData(current or "")))

    # ── guardado ──────────────────────────────────────────────────────────
    def _show(self, ok: bool, text: str) -> None:
        self.message.setText(text)
        self.message.setProperty("state", "success" if ok else "error")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setVisible(bool(text))

    def _save_classification(self) -> None:
        ok, message = self._m.classify_product(
            product_id=self._product_id,
            meat_category=self.category.currentData() or None,
            anatomical_region_id=self.region.currentData() or None,
            cut_classification_id=self.cut.currentData() or None,
            reason=self.reason.text().strip() or None)
        self._show(ok, "Clasificación guardada." if ok and message.startswith("MEAT_")
                   else message)
        if ok:
            self.reason.clear()
            self._info = self._m.product_classification(self._product_id)

    def _save_catch_weight(self) -> None:
        widgets = (self.min_weight, self.max_weight, self.avg_weight, self.tolerance)
        if not all(w.is_valid() for w in widgets):
            self._show(False, "Revisa los pesos y la tolerancia (0 a 100 %).")
            return
        ok, message = self._m.save_catch_weight(
            product_id=self._product_id, enabled=self.cw_enabled.isChecked(),
            nominal_unit_id=self.nominal_unit.currentData(),
            weight_unit_id=self.weight_unit.currentData(),
            minimum_weight=_dec(self.min_weight.decimal_value()),
            maximum_weight=_dec(self.max_weight.decimal_value()),
            average_weight=_dec(self.avg_weight.decimal_value()),
            tolerance_pct=_dec(self.tolerance.decimal_value()) or "0",
            price_basis=self.price_basis.currentData(),
            label_required=self.label_required.isChecked(),
            scale_barcode_enabled=self.scale_barcode.isChecked())
        self._show(ok, "Peso variable guardado." if ok else message)
