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
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.domain.products.enums import MEAT_PRODUCT_TYPES
from frontend.desktop.modules.products.view_models import (
    LIFECYCLE_ES,
    PRODUCT_TYPE_ES,
)

# Códigos de tipo cárnico que exigen especie (§5.3/§11). Sólo valores del enum de
# dominio — el formulario decide con esto cuándo mostrar la clasificación cárnica.
_MEAT_TYPE_CODES = frozenset(t.value for t in MEAT_PRODUCT_TYPES)
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

        # P0-04: en alta el código se genera automáticamente; sólo con permiso
        # PRODUCTS_OVERRIDE_CODE puede editarse manualmente.
        self._is_new = product_id is None
        self._can_override = bool(getattr(self._presenter, "can_override_code", False))
        self._manual_code = not self._is_new  # en edición el código ya es explícito

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.code = QLineEdit()
        self.name = QLineEdit()
        self.short_name = QLineEdit()
        # P0-03: unidad base por catálogo (guarda units_of_measure.id, no texto).
        self.base_unit = QComboBox()
        for unit in self._presenter.list_units():
            self.base_unit.addItem(f"{unit['code']} — {unit['name']}", unit["id"])
        self.product_type = QComboBox()
        for code, label in sorted(PRODUCT_TYPE_ES.items(), key=lambda kv: kv[1]):
            self.product_type.addItem(label, code)
        # P1-01: categoría por catálogo jerárquico (guarda product_categories.id).
        self.category = QComboBox()
        self.category.addItem("(Sin categoría)", None)
        for cat in self._presenter.list_categories():
            self.category.addItem(cat["label"], cat["id"])
        # P1-02: marca por catálogo (guarda product_brands.id).
        self.brand = QComboBox()
        self.brand.addItem("(Sin marca)", None)
        for br in self._presenter.list_brands():
            self.brand.addItem(br["label"], br["id"])
        # §5.2: especie por catálogo canónico (guarda species.id, nunca texto/UUID
        # a mano). Sólo aplica a tipos cárnicos → la sección se muestra/oculta según
        # el tipo. El primer item es un placeholder sin valor (obliga a elegir).
        self.species = QComboBox()
        self.species.addItem("(Selecciona especie)", None)
        for sp in self._presenter.list_species():
            self.species.addItem(sp["label"], sp["id"])
        # §6.1: el estado NO es editable desde el alta/edición (el alta nace en
        # DRAFT y sólo los casos de uso de ciclo de vida cambian el estado). Se
        # muestra como badge informativo, no como selector engañoso.
        self._state_badge = QLabel(LIFECYCLE_ES.get("DRAFT", "DRAFT"))
        self._state_badge.setObjectName("statusBadge")

        # Fila de código: campo + botón "Regenerar" + checkbox "manual" (si aplica).
        code_row = QWidget()
        code_layout = QHBoxLayout(code_row)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.addWidget(self.code)
        self._regen_btn = QPushButton("Regenerar")
        self._regen_btn.setObjectName("secondaryButton")
        self._regen_btn.clicked.connect(self._refresh_preview)
        code_layout.addWidget(self._regen_btn)
        self._manual_box = QCheckBox("Manual")
        self._manual_box.setToolTip("Asignar el código manualmente (requiere permiso)")
        self._manual_box.toggled.connect(self._on_manual_toggled)
        if self._is_new and self._can_override:
            code_layout.addWidget(self._manual_box)

        form.addRow("Código *", code_row)
        form.addRow("Nombre *", self.name)
        form.addRow("Nombre corto", self.short_name)
        form.addRow("Tipo *", self.product_type)
        form.addRow("Categoría", self.category)
        form.addRow("Marca", self.brand)
        form.addRow("Unidad base *", self.base_unit)
        form.addRow("Estado", self._state_badge)
        layout.addLayout(form)

        # §5.1/§5.2: clasificación cárnica — visible sólo para tipos cárnicos.
        self._meat_box = QGroupBox("Clasificación cárnica")
        meat_form = QFormLayout(self._meat_box)
        meat_form.addRow("Especie *", self.species)
        layout.addWidget(self._meat_box)

        # El tipo determina el prefijo del código y si aplica la sección cárnica.
        self.product_type.currentIndexChanged.connect(self._on_type_changed)
        self._apply_code_mode()
        self._apply_meat_visibility()

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
        # P1: galería de imágenes (sólo en edición: requiere product_id existente).
        if not self._is_new and getattr(self._presenter, "can_manage_images", False):
            self._btn_images = QPushButton("Imágenes…")
            self._btn_images.clicked.connect(self._open_gallery)
            buttons.addButton(self._btn_images, QDialogButtonBox.ActionRole)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if product_id:
            self._load(product_id)

    def _open_gallery(self) -> None:
        from frontend.desktop.modules.products.dialogs.image_gallery_dialog import (
            ImageGalleryDialog,
        )
        ImageGalleryDialog(self._presenter, product_id=self._product_id,
                           product_name=self.name.text() or "Producto",
                           parent=self).exec_()

    # ── carga (edición) ────────────────────────────────────────────────────
    def _load(self, product_id: str) -> None:
        row = self._presenter.get_product(product_id) or {}
        self.code.setText(str(row.get("code") or ""))
        self.name.setText(str(row.get("name") or ""))
        self.short_name.setText(str(row.get("short_name") or ""))
        self._select(self.base_unit, row.get("base_unit_id"))
        self._select(self.product_type, row.get("product_type"))
        self._select(self.category, row.get("category_id"))
        self._select(self.brand, row.get("brand_id"))
        self._select(self.species, row.get("species_id"))
        state = str(row.get("lifecycle_status") or "DRAFT")
        self._state_badge.setText(LIFECYCLE_ES.get(state, state))
        for key, cb in self._flag_boxes.items():
            cb.setChecked(bool(row.get(key)))
        self._apply_meat_visibility()

    @staticmethod
    def _select(combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    # ── código automático (P0-04) ────────────────────────────────────────────
    @property
    def _auto_code(self) -> bool:
        """True cuando el código lo genera el sistema (alta sin override manual)."""
        return self._is_new and not self._manual_code

    def _apply_code_mode(self) -> None:
        """Ajusta editabilidad del código y muestra la vista previa según el modo."""
        auto = self._auto_code
        # En alta auto el campo es de sólo lectura (se muestra la vista previa);
        # en edición sólo es editable con permiso de override.
        editable = (not auto) if self._is_new else self._can_override
        self.code.setReadOnly(not editable)
        self._regen_btn.setVisible(auto)
        if self._is_new and self._can_override:
            self._manual_box.setChecked(self._manual_code)
        if auto:
            self._refresh_preview()
        elif self._is_new:
            self.code.clear()

    def _on_manual_toggled(self, checked: bool) -> None:
        self._manual_code = bool(checked)
        self._apply_code_mode()

    def _on_type_changed(self, _index: int) -> None:
        if self._auto_code:
            self._refresh_preview()
        self._apply_meat_visibility()

    # ── clasificación cárnica (§5.1/§5.2) ─────────────────────────────────────
    def _is_meat_type(self) -> bool:
        return self.product_type.currentData() in _MEAT_TYPE_CODES

    def _apply_meat_visibility(self) -> None:
        """Muestra la sección cárnica sólo para tipos que exigen especie."""
        self._meat_box.setVisible(self._is_meat_type())

    def _refresh_preview(self) -> None:
        preview = self._presenter.preview_code(
            product_type=self.product_type.currentData())
        if preview:
            self.code.setText(preview)

    # ── guardado ───────────────────────────────────────────────────────────
    def _fields(self) -> dict:
        fields = {
            "name": self.name.text().strip(),
            "short_name": self.short_name.text().strip() or None,
            "product_type": self.product_type.currentData(),
            "category_id": self.category.currentData(),
            "brand_id": self.brand.currentData(),
            "base_unit_id": self.base_unit.currentData(),
            # §6.1: la UI no dicta el estado — el alta nace DRAFT y el update lo
            # preserva; el estado sólo cambia por los casos de uso de ciclo de vida.
            # §5.2: sólo se envía especie para tipos cárnicos (None en otros → el
            # dominio no la exige y no se ensucia el maestro).
            "species_id": self.species.currentData() if self._is_meat_type() else None,
        }
        if self._auto_code:
            # El código lo reserva el caso de uso dentro de su transacción.
            fields["auto_generate_code"] = True
            fields["code"] = ""
        else:
            fields["code"] = self.code.text().strip().upper()
        fields.update({key: cb.isChecked() for key, cb in self._flag_boxes.items()})
        return fields

    def _on_save(self) -> None:
        self._error.setText("")
        fields = self._fields()
        needs_code = not fields.get("auto_generate_code")
        if (needs_code and not fields["code"]) or not fields["name"] \
                or not fields["base_unit_id"]:
            self._error.setText("Código, Nombre y Unidad base son obligatorios.")
            return
        if self._is_meat_type() and not fields.get("species_id"):
            self._error.setText("Los productos cárnicos requieren especie.")
            return
        ok, message, _pid = self._presenter.save_product(
            product_id=self._product_id, fields=fields)
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            QMessageBox.warning(self, "No se pudo guardar", message)
