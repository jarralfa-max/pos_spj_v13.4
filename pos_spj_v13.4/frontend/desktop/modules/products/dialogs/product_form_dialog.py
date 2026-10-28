"""ProductFormDialog — alta/edición del maestro de productos (PROD-19 paso 7b).

UI-only: agrupa datos maestros, código de barras, imagen y regla de reposición.
La existencia y la regla permanecen bajo Inventario; la imagen usa el caso de
uso canónico de Productos. El precio permanece bajo Precios.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt

from frontend.desktop.components.dialogs import MessageDialog, StandardDialog

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from backend.domain.products.enums import MEAT_PRODUCT_TYPES
from frontend.desktop.components import (
    SearchableComboBox,
    create_secondary_button,
)
from frontend.desktop.components.barcode_input import BarcodeInput
from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.image_thumbnail import ImageThumbnail
from frontend.desktop.components.tabs import Tabs
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
        super().__init__(parent, width=720)
        self._presenter = presenter
        self._product_id = product_id
        self.setObjectName("productFormDialog")
        self.setWindowTitle("Editar producto" if product_id else "Nuevo producto")
        self.setMinimumWidth(640)
        self._flag_boxes: dict[str, QCheckBox] = {}
        self._pending_image: str | None = None
        self._master_saved = False

        # P0-04: en alta el código se genera automáticamente; sólo con permiso
        # PRODUCTS_OVERRIDE_CODE puede editarse manualmente.
        self._is_new = product_id is None
        self._can_override = bool(getattr(self._presenter, "can_override_code", False))
        self._manual_code = not self._is_new  # en edición el código ya es explícito

        layout = self.content_layout()
        self.tabs = Tabs(self)
        general_page = QWidget(self)
        general_layout = QVBoxLayout(general_page)
        operation_page = QWidget(self)
        operation_layout = QVBoxLayout(operation_page)
        stock_page = QWidget(self)
        stock_layout = QVBoxLayout(stock_page)
        images_page = QWidget(self)
        images_layout = QVBoxLayout(images_page)
        self.tabs.addTab(general_page, "General")
        self.tabs.addTab(operation_page, "Operación")
        self.tabs.addTab(stock_page, "Inventario")
        self.tabs.addTab(images_page, "Imágenes")
        layout.addWidget(self.tabs)
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
        general_layout.addLayout(form)

        # §5.1/§5.2: clasificación cárnica — visible sólo para tipos cárnicos.
        self._meat_box = QGroupBox("Clasificación cárnica")
        meat_form = QFormLayout(self._meat_box)
        meat_form.addRow("Especie *", self.species)
        operation_layout.addWidget(self._meat_box)

        # El tipo determina el prefijo del código y si aplica la sección cárnica.
        self.product_type.currentIndexChanged.connect(self._on_type_changed)
        self._apply_code_mode()
        self._apply_meat_visibility()

        self._build_barcode_box(general_layout)
        general_layout.addStretch(1)

        flags_box = QGroupBox("Capacidades")
        grid = QGridLayout(flags_box)
        for i, (key, label) in enumerate(_FLAGS):
            cb = QCheckBox(label)
            if key in ("sellable", "purchasable", "inventory_managed"):
                cb.setChecked(True)
            self._flag_boxes[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        operation_layout.addWidget(flags_box)
        operation_layout.addStretch(1)

        stock_hint = QLabel(
            "Mínimo de stock por almacén de esta sucursal. Al llegar al mínimo, "
            "Inventario puede generar una sugerencia de reposición. "
            "Las existencias se reciben o ajustan en Inventario.")
        stock_hint.setProperty("role", "muted")
        stock_hint.setWordWrap(True)
        stock_layout.addWidget(stock_hint)
        stock_form = QFormLayout()
        self.stock_warehouse = SearchableComboBox(placeholder="Selecciona almacén…")
        stock_lookup = getattr(self._presenter, "stock_warehouses", None)
        stock_options = stock_lookup() if callable(stock_lookup) else []
        self.stock_warehouse.set_options(stock_options if isinstance(stock_options, list) else [])
        self.stock_warehouse.selection_changed.connect(self._load_stock_rule)
        self.stock_minimum = DecimalInput(precision=3, minimum="0")
        self.stock_target = DecimalInput(precision=3, minimum="0")
        self.stock_target.setToolTip("Cantidad objetivo tras reponer; debe ser igual o mayor al mínimo.")
        stock_form.addRow("Almacén *", self.stock_warehouse)
        stock_form.addRow("Mínimo *", self.stock_minimum)
        stock_form.addRow("Objetivo de reposición *", self.stock_target)
        stock_layout.addLayout(stock_form)
        self.stock_hint = QLabel("Selecciona un almacén para configurar su mínimo.")
        self.stock_hint.setWordWrap(True)
        stock_hint.setProperty("role", "muted")
        stock_layout.addWidget(self.stock_hint)
        stock_layout.addStretch(1)
        can_stock = bool(getattr(self._presenter, "can_manage_stock_minimum", False))
        for widget in (self.stock_warehouse, self.stock_minimum, self.stock_target):
            widget.setEnabled(can_stock)
        if not can_stock:
            self.stock_hint.setText("Requiere el permiso de Inventario para configurar reposición.")

        image_hint = QLabel("La imagen principal aparece en las tarjetas del POS. "
                            "Puedes elegirla ahora y se guardará al crear el producto.")
        image_hint.setProperty("role", "muted")
        image_hint.setWordWrap(True)
        images_layout.addWidget(image_hint)
        self.image_preview = ImageThumbnail(self, width=220, height=220)
        images_layout.addWidget(self.image_preview)
        self.image_button = create_secondary_button(self, "Seleccionar imagen…")
        self.image_button.clicked.connect(self._choose_image)
        images_layout.addWidget(self.image_button)
        self.image_button.setEnabled(bool(getattr(self._presenter, "can_manage_images", False)))
        if not self._is_new and self.image_button.isEnabled():
            gallery_button = create_secondary_button(self, "Administrar galería y fondo…")
            gallery_button.clicked.connect(self._open_gallery)
            images_layout.addWidget(gallery_button)
        images_layout.addStretch(1)

        self._error = QLabel()
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Save).setDefault(False)
        buttons.button(QDialogButtonBox.Save).setAutoDefault(False)
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

    def keyPressEvent(self, event) -> None:
        """El Enter de un escáner HID no confirma accidentalmente el alta."""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            return
        super().keyPressEvent(event)

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar imagen del producto", "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.gif *.bmp)")
        if path:
            self._pending_image = path
            self.image_preview.set_image(path, placeholder=self.name.text() or "Producto")

    def _load_stock_rule(self, warehouse_id) -> None:
        self.stock_minimum.set_decimal(None)
        self.stock_target.set_decimal(None)
        if not warehouse_id or not self._product_id:
            return
        rule = self._presenter.stock_minimum(self._product_id, warehouse_id)
        if rule is not None:
            self.stock_minimum.set_decimal(rule["minimum"])
            self.stock_target.set_decimal(rule["target"])

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
        image_lookup = getattr(self._presenter, "list_images", None)
        images = image_lookup(product_id) if callable(image_lookup) else []
        if not isinstance(images, list):
            images = []
        primary = next((item for item in images if item.get("is_primary")), None)
        if primary is not None:
            self.image_preview.set_image(primary.get("uri"),
                                         placeholder=self.name.text() or "Producto")

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
        warehouse = self._combo_value(self.stock_warehouse)
        wants_rule = (self.stock_minimum.text().strip() or self.stock_target.text().strip())
        if wants_rule:
            if not warehouse or not self._presenter.can_manage_stock_minimum:
                self.tabs.setCurrentIndex(2)
                self._error.setText("Selecciona un almacén y verifica el permiso de reposición.")
                return
            if not (self.stock_minimum.is_valid() and self.stock_target.is_valid()):
                self.tabs.setCurrentIndex(2)
                self._error.setText("Revisa el mínimo y el objetivo de reposición.")
                return
            if self.stock_target.decimal_value() < self.stock_minimum.decimal_value():
                self.tabs.setCurrentIndex(2)
                self._error.setText("El objetivo debe ser mayor o igual que el mínimo.")
                return
        if self._master_saved:
            ok, message, _pid = True, "Producto guardado", self._product_id
        else:
            ok, message, _pid = self._presenter.save_product(
                product_id=self._product_id, fields=fields)
        if ok:
            self._product_id = _pid or self._product_id
            self._master_saved = True
            if wants_rule:
                saved, reason = self._presenter.save_stock_minimum(
                    self._product_id, warehouse, minimum=self.stock_minimum.decimal_value(),
                    target=self.stock_target.decimal_value())
                if not saved:
                    self.tabs.setCurrentIndex(2)
                    self._error.setText(
                        f"Producto guardado, pero el mínimo quedó pendiente: {reason} "
                        "Corrige el dato y vuelve a guardar.")
                    return
            if self._pending_image:
                saved, reason = self._presenter.add_image(
                    product_id=self._product_id, uri=self._pending_image,
                    alt_text=Path(self._pending_image).name, make_primary=True)
                if not saved:
                    self.tabs.setCurrentIndex(3)
                    self._error.setText(
                        f"Producto guardado, pero la imagen quedó pendiente: {reason} "
                        "Vuelve a guardar para reintentar.")
                    return
                self._pending_image = None
            self.accept()
        else:
            self._error.setText(message)
            MessageDialog.warning(self, "No se pudo guardar", message)
