"""ProductFormDialog — alta/edición del maestro de productos (PROD-19 paso 7b).

UI-only: captura los datos MAESTRO (identidad, tipo, unidad base, estado, flags de
capacidad) y delega el guardado en ``ProductsPresenter.save_product`` (use cases
canónicos). Sin SQL ni lógica de negocio. El precio se gestiona en el módulo de
Precios; la existencia en Inventario — este formulario NO los captura.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from frontend.desktop.modules.products.view_models import (
    LIFECYCLE_ES,
    PRODUCT_TYPE_ES,
)

_LIFECYCLE_CHOICES = ("DRAFT", "UNDER_REVIEW", "ACTIVE", "INACTIVE")
_FLAGS = (
    ("sellable", "Vendible"),
    ("purchasable", "Comprable"),
    ("inventory_managed", "Controla inventario"),
    ("producible", "Producible"),
    ("recipe_allowed", "Admite receta"),
    ("bundle_allowed", "Admite combo"),
    ("lot_controlled", "Controla lote"),
    ("expiration_controlled", "Controla caducidad"),
    ("catch_weight_enabled", "Peso variable"),
    ("quality_controlled", "Control de calidad"),
    ("traceability_required", "Trazabilidad"),
    ("internal_only", "Solo interno"),
)


class ProductFormDialog(QDialog):
    def __init__(self, presenter, product_id: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._product_id = product_id
        self.setObjectName("productFormDialog")
        self.setWindowTitle("Editar producto" if product_id else "Nuevo producto")
        self.setMinimumWidth(460)
        self._flag_boxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.code = QLineEdit()
        self.name = QLineEdit()
        self.short_name = QLineEdit()
        self.base_unit = QLineEdit()
        self.base_unit.setPlaceholderText("KG, PZA, LT…")
        self.product_type = QComboBox()
        for code, label in sorted(PRODUCT_TYPE_ES.items(), key=lambda kv: kv[1]):
            self.product_type.addItem(label, code)
        self.lifecycle = QComboBox()
        for code in _LIFECYCLE_CHOICES:
            self.lifecycle.addItem(LIFECYCLE_ES.get(code, code), code)

        form.addRow("Código *", self.code)
        form.addRow("Nombre *", self.name)
        form.addRow("Nombre corto", self.short_name)
        form.addRow("Tipo *", self.product_type)
        form.addRow("Unidad base *", self.base_unit)
        form.addRow("Estado", self.lifecycle)
        layout.addLayout(form)

        flags_box = QGroupBox("Capacidades")
        grid = QGridLayout(flags_box)
        for i, (key, label) in enumerate(_FLAGS):
            cb = QCheckBox(label)
            if key in ("sellable", "purchasable", "inventory_managed"):
                cb.setChecked(True)
            self._flag_boxes[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        layout.addWidget(flags_box)

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

        if product_id:
            self._load(product_id)

    # ── carga (edición) ────────────────────────────────────────────────────
    def _load(self, product_id: str) -> None:
        row = self._presenter.get_product(product_id) or {}
        self.code.setText(str(row.get("code") or ""))
        self.name.setText(str(row.get("name") or ""))
        self.short_name.setText(str(row.get("short_name") or ""))
        self.base_unit.setText(str(row.get("base_unit_id") or ""))
        self._select(self.product_type, row.get("product_type"))
        self._select(self.lifecycle, row.get("lifecycle_status"))
        for key, cb in self._flag_boxes.items():
            cb.setChecked(bool(row.get(key)))

    @staticmethod
    def _select(combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    # ── guardado ───────────────────────────────────────────────────────────
    def _fields(self) -> dict:
        fields = {
            "code": self.code.text().strip().upper(),
            "name": self.name.text().strip(),
            "short_name": self.short_name.text().strip() or None,
            "product_type": self.product_type.currentData(),
            "base_unit_id": self.base_unit.text().strip().upper(),
            "lifecycle_status": self.lifecycle.currentData(),
        }
        fields.update({key: cb.isChecked() for key, cb in self._flag_boxes.items()})
        return fields

    def _on_save(self) -> None:
        self._error.setText("")
        fields = self._fields()
        if not fields["code"] or not fields["name"] or not fields["base_unit_id"]:
            self._error.setText("Código, Nombre y Unidad base son obligatorios.")
            return
        ok, message, _pid = self._presenter.save_product(
            product_id=self._product_id, fields=fields)
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            QMessageBox.warning(self, "No se pudo guardar", message)
