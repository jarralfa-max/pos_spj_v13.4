"""ProfilesDialog — vida útil, calidad y logística de UN producto (§18-20, PROD-22).

Productos DEFINE los perfiles; Calidad e Inventario los ejecutan. Tres pestañas,
cada una con su propio «Guardar» (cada perfil es un caso de uso distinto, con su
propia validación y auditoría). Números con IntegerInput/DecimalInput: nunca
texto libre ni float.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components.buttons import create_primary_button
from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.integer_input import IntegerInput
from frontend.desktop.components.tabs import Tabs
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.modules.products.product_codes_profiles_presenter import (
    STORAGE_CONDITION_ES,
)
from frontend.desktop.themes.tokens import DialogMetrics


def _dec(value) -> str | None:
    """DecimalInput → texto para el comando (Decimal en el dominio, nunca float)."""
    return None if value is None else str(value)


class ProfilesDialog(StandardDialog):
    def __init__(self, presenter, *, product_id: str, product_name: str,
                 parent=None) -> None:
        super().__init__(parent, title=f"Calidad, vida útil y logística de «{product_name}»",
                         width=DialogMetrics.WIDTH_LG)
        self.setObjectName("productProfilesDialog")
        self.setMinimumSize(720, 560)
        self._p = presenter
        self._product_id = product_id
        layout = self.content_layout()

        self.tabs = Tabs(self)
        self.tabs.addTab(self._shelf_tab(), "Vida útil")
        self.tabs.addTab(self._quality_tab(), "Calidad")
        self.tabs.addTab(self._logistics_tab(), "Logística y cadena de frío")
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

        can_edit = bool(getattr(self._p, "can_edit_profiles", False))
        for button in (self.btn_shelf, self.btn_quality, self.btn_logistics):
            button.setEnabled(can_edit)
        self._load()

    # ── pestañas ──────────────────────────────────────────────────────────
    def _tab(self) -> tuple[QWidget, QVBoxLayout]:
        tab = QWidget()
        box = QVBoxLayout(tab)
        return tab, box

    def _shelf_tab(self) -> QWidget:
        tab, box = self._tab()
        form = QFormLayout()
        self.shelf_days = IntegerInput(minimum=0, maximum=3650)
        self.min_receipt = IntegerInput(minimum=0, maximum=3650)
        self.min_sale = IntegerInput(minimum=0, maximum=3650)
        self.storage = QComboBox()
        for key, label in STORAGE_CONDITION_ES.items():
            self.storage.addItem(label, key)
        self.opened_days = IntegerInput(minimum=0, maximum=3650)
        self.frozen_days = IntegerInput(minimum=0, maximum=3650)
        self.thawed_days = IntegerInput(minimum=0, maximum=3650)
        for label, widget in (("Vida útil (días) *", self.shelf_days),
                              ("Mínimo restante al recibir (días)", self.min_receipt),
                              ("Mínimo restante para vender (días)", self.min_sale),
                              ("Conservación", self.storage),
                              ("Vida útil abierto (días)", self.opened_days),
                              ("Vida útil congelado (días)", self.frozen_days),
                              ("Vida útil descongelado (días)", self.thawed_days)):
            form.addRow(label, widget)
        box.addLayout(form)
        self.btn_shelf = create_primary_button(self, "Guardar vida útil")
        self.btn_shelf.clicked.connect(self._save_shelf)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.btn_shelf)
        box.addLayout(row)
        box.addStretch(1)
        return tab

    def _quality_tab(self) -> QWidget:
        tab, box = self._tab()
        grid = QGridLayout()
        self.q_checks = {}
        for i, (key, label) in enumerate((
                ("inspection_required", "Inspección al recibir"),
                ("temperature_required", "Revisión de temperatura"),
                ("weight_check_required", "Revisión de peso"),
                ("organoleptic_check_required", "Revisión organoléptica"),
                ("quarantine_required", "Cuarentena hasta liberar"))):
            cb = QCheckBox(label)
            self.q_checks[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        box.addLayout(grid)
        form = QFormLayout()
        self.fat_min = DecimalInput(precision=2, minimum="0", maximum="100", nullable=True)
        self.fat_max = DecimalInput(precision=2, minimum="0", maximum="100", nullable=True)
        self.moist_min = DecimalInput(precision=2, minimum="0", maximum="100", nullable=True)
        self.moist_max = DecimalInput(precision=2, minimum="0", maximum="100", nullable=True)
        self.color = StandardLineEdit(placeholder="Opcional")
        self.odor = StandardLineEdit(placeholder="Opcional")
        self.packaging = StandardLineEdit(placeholder="Opcional")
        self.documentation = StandardLineEdit(placeholder="Ej. certificado sanitario")
        for label, widget in (("Grasa mínima (%)", self.fat_min),
                              ("Grasa máxima (%)", self.fat_max),
                              ("Humedad mínima (%)", self.moist_min),
                              ("Humedad máxima (%)", self.moist_max),
                              ("Color", self.color), ("Olor", self.odor),
                              ("Empaque", self.packaging),
                              ("Documentación", self.documentation)):
            form.addRow(label, widget)
        box.addLayout(form)
        self.btn_quality = create_primary_button(self, "Guardar calidad")
        self.btn_quality.clicked.connect(self._save_quality)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.btn_quality)
        box.addLayout(row)
        box.addStretch(1)
        return tab

    def _logistics_tab(self) -> QWidget:
        tab, box = self._tab()
        form = QFormLayout()
        self.gross = DecimalInput(precision=3, minimum="0", nullable=True)
        self.net = DecimalInput(precision=3, minimum="0", nullable=True)
        self.dimensions = StandardLineEdit(placeholder="Largo x ancho x alto (cm)")
        self.st_min = DecimalInput(precision=1, minimum="-60", maximum="60", nullable=True)
        self.st_max = DecimalInput(precision=1, minimum="-60", maximum="60", nullable=True)
        self.tr_min = DecimalInput(precision=1, minimum="-60", maximum="60", nullable=True)
        self.tr_max = DecimalInput(precision=1, minimum="-60", maximum="60", nullable=True)
        for label, widget in (("Peso bruto (kg)", self.gross), ("Peso neto (kg)", self.net),
                              ("Dimensiones", self.dimensions),
                              ("Almacenamiento mín. (°C)", self.st_min),
                              ("Almacenamiento máx. (°C)", self.st_max),
                              ("Transporte mín. (°C)", self.tr_min),
                              ("Transporte máx. (°C)", self.tr_max)):
            form.addRow(label, widget)
        box.addLayout(form)
        grid = QGridLayout()
        self.l_checks = {}
        for i, (key, label) in enumerate((("perishable", "Perecedero"),
                                          ("chilled", "Refrigerado"), ("frozen", "Congelado"),
                                          ("fragile", "Frágil"), ("stackable", "Apilable"))):
            cb = QCheckBox(label)
            self.l_checks[key] = cb
            grid.addWidget(cb, i // 3, i % 3)
        self.l_checks["stackable"].setChecked(True)
        box.addLayout(grid)
        self.cold_chain = QLabel("")
        self.cold_chain.setProperty("role", "muted")
        box.addWidget(self.cold_chain)
        self.btn_logistics = create_primary_button(self, "Guardar logística")
        self.btn_logistics.clicked.connect(self._save_logistics)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.btn_logistics)
        box.addLayout(row)
        box.addStretch(1)
        return tab

    # ── carga ─────────────────────────────────────────────────────────────
    def _load(self) -> None:
        data = self._p.profiles(self._product_id)
        shelf = data.get("shelf_life") or {}
        if shelf:
            self.shelf_days.setValue(int(shelf.get("shelf_life_days") or 0))
            self.min_receipt.setValue(int(shelf.get("minimum_remaining_for_receipt") or 0))
            self.min_sale.setValue(int(shelf.get("minimum_remaining_for_sale") or 0))
            self.storage.setCurrentIndex(max(0, self.storage.findData(
                shelf.get("storage_condition") or "AMBIENT")))
            self.opened_days.setValue(int(shelf.get("opened_shelf_life_days") or 0))
            self.frozen_days.setValue(int(shelf.get("frozen_shelf_life_days") or 0))
            self.thawed_days.setValue(int(shelf.get("thawed_shelf_life_days") or 0))
        quality = data.get("quality") or {}
        for key, cb in self.q_checks.items():
            cb.setChecked(bool(quality.get(key)))
        for widget, key in ((self.fat_min, "fat_pct_min"), (self.fat_max, "fat_pct_max"),
                            (self.moist_min, "moisture_pct_min"),
                            (self.moist_max, "moisture_pct_max")):
            widget.set_decimal(quality.get(key))
        for widget, key in ((self.color, "color_requirement"), (self.odor, "odor_requirement"),
                            (self.packaging, "packaging_requirement"),
                            (self.documentation, "documentation_requirement")):
            widget.setText(quality.get(key) or "")
        logistics = data.get("logistics") or {}
        for widget, key in ((self.gross, "gross_weight"), (self.net, "net_weight"),
                            (self.st_min, "storage_temp_min"), (self.st_max, "storage_temp_max"),
                            (self.tr_min, "transport_temp_min"),
                            (self.tr_max, "transport_temp_max")):
            widget.set_decimal(logistics.get(key))
        self.dimensions.setText(logistics.get("dimensions") or "")
        if logistics:
            for key, cb in self.l_checks.items():
                cb.setChecked(bool(logistics.get(key)))
        self.cold_chain.setText("Requiere cadena de frío." if logistics.get("requires_cold_chain")
                                else "")

    # ── guardado ──────────────────────────────────────────────────────────
    def _show(self, ok: bool, text: str) -> None:
        self.message.setText(text)
        self.message.setProperty("state", "success" if ok else "error")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setVisible(bool(text))

    def _done(self, result: tuple[bool, str], saved: str) -> None:
        ok, message = result
        self._show(ok, saved if ok else message)
        if ok:
            self._load()

    def _save_shelf(self) -> None:
        if self.shelf_days.value() <= 0:
            self._show(False, "La vida útil debe ser de al menos 1 día.")
            return
        self._done(self._p.save_shelf_life(
            product_id=self._product_id, shelf_life_days=self.shelf_days.value(),
            minimum_remaining_for_receipt=self.min_receipt.value(),
            minimum_remaining_for_sale=self.min_sale.value(),
            storage_condition=self.storage.currentData(),
            opened_shelf_life_days=self.opened_days.value(),
            frozen_shelf_life_days=self.frozen_days.value(),
            thawed_shelf_life_days=self.thawed_days.value()), "Vida útil guardada.")

    def _save_quality(self) -> None:
        invalid = [w for w in (self.fat_min, self.fat_max, self.moist_min, self.moist_max)
                   if not w.is_valid()]
        if invalid:
            self._show(False, "Los porcentajes deben estar entre 0 y 100.")
            return
        self._done(self._p.save_quality(
            product_id=self._product_id,
            **{key: cb.isChecked() for key, cb in self.q_checks.items()},
            fat_pct_min=_dec(self.fat_min.decimal_value()),
            fat_pct_max=_dec(self.fat_max.decimal_value()),
            moisture_pct_min=_dec(self.moist_min.decimal_value()),
            moisture_pct_max=_dec(self.moist_max.decimal_value()),
            color_requirement=self.color.text().strip() or None,
            odor_requirement=self.odor.text().strip() or None,
            packaging_requirement=self.packaging.text().strip() or None,
            documentation_requirement=self.documentation.text().strip() or None),
            "Perfil de calidad guardado.")

    def _save_logistics(self) -> None:
        widgets = (self.gross, self.net, self.st_min, self.st_max, self.tr_min, self.tr_max)
        if not all(w.is_valid() for w in widgets):
            self._show(False, "Revisa pesos y temperaturas (temperaturas entre -60 y 60 °C).")
            return
        self._done(self._p.save_logistics(
            product_id=self._product_id,
            gross_weight=_dec(self.gross.decimal_value()),
            net_weight=_dec(self.net.decimal_value()),
            dimensions=self.dimensions.text().strip() or None,
            storage_temp_min=_dec(self.st_min.decimal_value()),
            storage_temp_max=_dec(self.st_max.decimal_value()),
            transport_temp_min=_dec(self.tr_min.decimal_value()),
            transport_temp_max=_dec(self.tr_max.decimal_value()),
            **{key: cb.isChecked() for key, cb in self.l_checks.items()}),
            "Perfil logístico guardado.")
