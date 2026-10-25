"""ProductFormDialog — alta/edición del maestro de productos (PROD-19 paso 7b).

UI-only: captura los datos MAESTRO (identidad, tipo, unidad base, estado, flags de
capacidad) y delega el guardado en ``ProductsPresenter.save_product`` (use cases
canónicos). PROD-23: en el alta puede capturarse el código de barras principal
(escaneado, tecleado o interno generado); se asigna en la misma transacción. Sin SQL ni lógica de negocio. El precio se gestiona en el módulo de
Precios; la existencia en Inventario — este formulario NO los captura.
"""

from __future__ import annotations

from frontend.desktop.components.dialogs import StandardDialog

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QWidget,
)

from backend.domain.products.enums import MEAT_PRODUCT_TYPES
from frontend.desktop.components import (
    SearchableComboBox,
    create_secondary_button,
)
from frontend.desktop.components.barcode_input import BarcodeInput
from frontend.desktop.modules.products.product_codes_profiles_presenter import (
    BARCODE_TYPE_ES,
)
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


class ProductFormDialog(StandardDialog):
    def __init__(self, presenter, product_id: str | None = None, parent=None) -> None:
        super().__init__(parent, width=460)
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

        layout = self.content_layout()
        form = QFormLayout()
        self.code = QLineEdit()
        self.name = QLineEdit()
        self.short_name = QLineEdit()
        # §7.1/§20: los catálogos (unidad/categoría/marca/especie) usan
        # SearchableComboBox (búsqueda + placeholder que obliga a elegir), no listas
        # QComboBox largas ni texto libre. Guardan siempre el UUID del catálogo.
        self.base_unit = SearchableComboBox(placeholder="Unidad base…")
        self.base_unit.set_options(
            [(u["id"], f"{u['code']} — {u['name']}") for u in self._presenter.list_units()])
        # El tipo es un enum fijo → QComboBox es aceptable (no es un catálogo grande).
        self.product_type = QComboBox()
        for code, label in sorted(PRODUCT_TYPE_ES.items(), key=lambda kv: kv[1]):
            self.product_type.addItem(label, code)
        self.category = SearchableComboBox(placeholder="(Sin categoría)")
        self.category.set_options(
            [(c["id"], c["label"]) for c in self._presenter.list_categories()])
        self.brand = SearchableComboBox(placeholder="(Sin marca)")
        self.brand.set_options(
            [(b["id"], b["label"]) for b in self._presenter.list_brands()])
        # §5.2: especie por catálogo canónico; sólo aplica a tipos cárnicos.
        self.species = SearchableComboBox(placeholder="Especie…")
        self.species.set_options(
            [(s["id"], s["label"]) for s in self._presenter.list_species()])
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
        self._regen_btn = create_secondary_button(text="Regenerar")
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

        self._build_barcode_box(layout)

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
            self._btn_images = create_secondary_button(text="Imágenes…")
            self._btn_images.clicked.connect(self._open_gallery)
            buttons.addButton(self._btn_images, QDialogButtonBox.ActionRole)
        # PROD-23: en edición los códigos de barras se gestionan desde aquí también.
        if not self._is_new and self._codes is not None:
            self._btn_barcodes = create_secondary_button(text="Códigos de barras…")
            self._btn_barcodes.clicked.connect(self._open_barcodes)
            buttons.addButton(self._btn_barcodes, QDialogButtonBox.ActionRole)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        self.add_footer_widget(buttons)

        if product_id:
            self._load(product_id)
        else:
            self._apply_defaults()

    def _apply_defaults(self) -> None:
        """PROD-22: tipo y unidad por omisión de Productos → Configuración."""
        settings = getattr(self._presenter, "settings", None)
        defaults = settings.defaults() if settings is not None else {}
        if defaults.get("product_type"):
            self._select(self.product_type, defaults["product_type"])
        code = (defaults.get("base_unit_code") or "").upper()
        if code:
            unit = next((u for u in self._presenter.list_units()
                         if (u.get("code") or "").upper() == code), None)
            if unit is not None:
                self.base_unit.set_current_id(unit["id"])

    # ── código de barras (PROD-23) ─────────────────────────────────────────
    def _build_barcode_box(self, layout) -> None:
        """Sección opcional del ALTA: el código que leerá el POS."""
        self._codes = getattr(self._presenter, "codes_profiles", None)
        self.barcode_box = QGroupBox("Lleva código de barras")
        self.barcode_box.setCheckable(True)
        self.barcode_box.setChecked(False)
        form = QFormLayout(self.barcode_box)
        self.barcode_value = BarcodeInput(clear_after_scan=False)
        self.barcode_value.setAccessibleName("Código de barras")
        self.barcode_value.textEdited.connect(self._guess_barcode_type)
        self.barcode_value.scanned.connect(self._guess_barcode_type)
        self.barcode_type = QComboBox()
        for key, label in BARCODE_TYPE_ES.items():
            self.barcode_type.addItem(label, key)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.barcode_value, 1)
        self.btn_generate_barcode = create_secondary_button(text="Generar interno")
        self.btn_generate_barcode.setToolTip(
            "Para productos sin código de fabricante: EAN-13 interno (prefijo 04) "
            "que no se repite.")
        self.btn_generate_barcode.clicked.connect(self._generate_barcode)
        row_layout.addWidget(self.btn_generate_barcode)
        form.addRow("Código *", row)
        form.addRow("Tipo *", self.barcode_type)
        hint = QLabel("Escanéalo o escríbelo; si no trae de fabricante, genera uno "
                      "interno. Se guarda como principal (el que lee el POS).")
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        form.addRow(hint)
        layout.addWidget(self.barcode_box)
        can = bool(self._codes is not None
                   and getattr(self._codes, "can_manage_barcodes", False))
        self._barcode_enabled = self._is_new and can
        self.barcode_box.setVisible(self._barcode_enabled)

    def _guess_barcode_type(self, text: str) -> None:
        value = (text or "").strip()
        if value.isdigit() and len(value) in (13, 12):
            self._select(self.barcode_type, "EAN" if len(value) == 13 else "UPC")

    def _generate_barcode(self) -> None:
        value = self._codes.preview_internal_barcode() if self._codes is not None else ""
        if not value:
            self._error.setText("No se pudo generar un código interno; escríbelo.")
            return
        self.barcode_value.setText(value)
        self._select(self.barcode_type, "EAN")

    def _open_barcodes(self) -> None:
        from frontend.desktop.modules.products.dialogs.barcodes_dialog import (
            BarcodesDialog,
        )
        BarcodesDialog(self._codes, product_id=self._product_id,
                       product_name=self.name.text() or "Producto", parent=self).exec_()

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
        self.base_unit.set_current_id(row.get("base_unit_id"))
        self._select(self.product_type, row.get("product_type"))
        self.category.set_current_id(row.get("category_id"))
        self.brand.set_current_id(row.get("brand_id"))
        self.species.set_current_id(row.get("species_id"))
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

    @staticmethod
    def _combo_value(combo: SearchableComboBox):
        """UUID del catálogo seleccionado o None cuando está el placeholder.

        SearchableComboBox devuelve un centinela (_PLACEHOLDER_ID) mientras no
        se elige nada; el maestro debe guardar None, no el centinela.
        """
        return combo.current_id() if combo.has_selection() else None

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
            "category_id": self._combo_value(self.category),
            "brand_id": self._combo_value(self.brand),
            "base_unit_id": self._combo_value(self.base_unit),
            # §6.1: la UI no dicta el estado — el alta nace DRAFT y el update lo
            # preserva; el estado sólo cambia por los casos de uso de ciclo de vida.
            # §5.2: sólo se envía especie para tipos cárnicos (None en otros → el
            # dominio no la exige y no se ensucia el maestro).
            "species_id": self._combo_value(self.species) if self._is_meat_type() else None,
        }
        if self._auto_code:
            # El código lo reserva el caso de uso dentro de su transacción.
            fields["auto_generate_code"] = True
            fields["code"] = ""
        else:
            fields["code"] = self.code.text().strip().upper()
        fields.update({key: cb.isChecked() for key, cb in self._flag_boxes.items()})
        if self._barcode_enabled and self.barcode_box.isChecked():
            fields["initial_barcode"] = self.barcode_value.code()
            fields["initial_barcode_type"] = self.barcode_type.currentData()
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
        if "initial_barcode" in fields and not fields["initial_barcode"]:
            self._error.setText("Escanea o escribe el código de barras (o genera uno "
                                "interno), o desmarca «Lleva código de barras».")
            return
        ok, message, _pid = self._presenter.save_product(
            product_id=self._product_id, fields=fields)
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            QMessageBox.warning(self, "No se pudo guardar", message)
