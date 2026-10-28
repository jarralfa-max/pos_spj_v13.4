"""Product catalog page (§42, §43) — searchable master catalog.

UI only: a SearchInput feeding the presenter, and a StandardTable of products.
No SQL, no business logic, no local styles; the presenter formats rows.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    SearchInput,
    StandardTable,
)
from frontend.desktop.components.buttons import (
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import MessageDialog
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class ProductCatalogPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productCatalogPage")
        self._presenter = presenter
        self._data_changed = None  # señal central (§8.3), cableada por el host

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Catálogo de Productos",
            subtitle="Maestro de productos con búsqueda por nombre o código.",
            icon=getattr(Icons, "CATALOG", None), compact=True)
        layout.addWidget(self.header)

        # PROD-22: a 1366×768 la barra de 11 botones se salía de la pantalla,
        # aplastaba el buscador y, como la página es la más ancha del módulo,
        # imponía scroll horizontal a TODAS las secciones. Ahora: búsqueda y
        # acciones del maestro a la vista; lo que abre otra ficha del producto
        # va en «Más acciones».
        toolbar = QHBoxLayout()
        toolbar.setSpacing(Spacing.SM)
        self.search = SearchInput(placeholder="Buscar producto por nombre o código…")
        self.search.setMinimumWidth(180)
        self.search.textChanged.connect(self._on_search)
        # §42: cárnicos, internos y materiales son filtros de este catálogo,
        # no secciones aparte que repetirían la misma tabla.
        self.family = QComboBox()
        self.family.setObjectName("productCatalogFamily")
        self.family.setAccessibleName("Familia de productos")
        # El combo no debe imponer su texto más largo como ancho mínimo.
        self.family.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.family.setMinimumContentsLength(14)
        for value, label in getattr(self._presenter, "CATALOG_FAMILY_OPTIONS",
                                    (("", "Todos los productos"),)):
            self.family.addItem(label, value)
        self.family.currentIndexChanged.connect(lambda _i: self.refresh(
            query=self.search.text() or None))
        toolbar.addWidget(self.family)
        toolbar.addWidget(self.search, 1)
        self.btn_new = create_primary_button(self, "Nuevo")
        self.btn_edit = create_secondary_button(self, "Editar")
        # §6.3: acciones de ciclo de vida (el estado no se edita en el formulario).
        self.btn_submit = create_secondary_button(self, "Enviar a revisión")
        self.btn_activate = create_secondary_button(self, "Activar")
        self.btn_more = create_secondary_button(
            self, "Más acciones", "Variantes, recetas, rendimientos, despiece, combos, "
            "unidades de compra e imágenes del producto seleccionado")
        self.btn_new.clicked.connect(lambda: self._open_form(None))
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_submit.clicked.connect(self._submit_selected)
        self.btn_activate.clicked.connect(self._activate_selected)
        self.btn_new.setEnabled(getattr(self._presenter, "can_create", False))
        self.btn_edit.setEnabled(getattr(self._presenter, "can_edit", False))
        self.btn_submit.setEnabled(getattr(self._presenter, "can_submit", False))
        self.btn_activate.setEnabled(getattr(self._presenter, "can_activate", False))

        self.more_menu = QMenu(self.btn_more)
        p = self._presenter
        self.act_variants = self._menu_action(
            "Variantes…", self._open_variants, getattr(p, "can_generate_variants", False))
        self.act_recipes = self._menu_action(
            "Recetas…", self._open_recipes, getattr(p, "can_manage_recipes", False))
        self.act_yields = self._menu_action(
            "Rendimientos…", self._open_yields, getattr(p, "can_manage_yields", False))
        self.act_cutting = self._menu_action(
            "Despiece…", self._open_cutting, getattr(p, "can_manage_cutting", False))
        self.act_bundles = self._menu_action(
            "Combos…", self._open_bundles, getattr(p, "can_manage_bundles", False))
        self.more_menu.addSeparator()
        # Ver es libre; agregar/retirar lo gatea el propio diálogo.
        self.act_purchase_units = self._menu_action(
            "Unidades de compra…", self._open_purchase_units,
            callable(getattr(p, "purchase_unit_profile", None)))
        self.act_images = self._menu_action(
            "Imágenes…", self._open_images, getattr(p, "can_manage_images", False))
        codes = getattr(p, "codes_profiles", None)
        self.act_barcodes = self._menu_action(
            "Códigos de barras…", self._open_barcodes, codes is not None)
        self.act_profiles = self._menu_action(
            "Calidad, vida útil y logística…", self._open_profiles, codes is not None)
        self.act_meat = self._menu_action(
            "Clasificación cárnica y peso variable…", self._open_meat,
            getattr(p, "meat", None) is not None)
        self.btn_more.setMenu(self.more_menu)
        for b in (self.btn_new, self.btn_edit, self.btn_submit, self.btn_activate,
                  self.btn_more):
            toolbar.addWidget(b)
        layout.addLayout(toolbar)

        self.table = StandardTable(columns=[
            ColumnSpec("Código", "code"),
            ColumnSpec("Nombre", "name"),
            ColumnSpec("Tipo", "product_type"),
            ColumnSpec("Estado", "lifecycle_status"),
            ColumnSpec("Cárnico", "is_meat"),
        ])
        layout.addWidget(self.table, 1)
        self.refresh()

    def set_data_changed_signal(self, signal) -> None:
        """§8.3: guarda la señal central para emitirla tras mutaciones."""
        self._data_changed = signal

    def _emit_changed(self) -> None:
        if self._data_changed is not None:
            self._data_changed.emit()

    def _on_search(self, text) -> None:
        self.refresh(query=text)

    def _menu_action(self, text: str, slot, enabled: bool):
        action = self.more_menu.addAction(text)
        action.triggered.connect(slot)
        action.setEnabled(bool(enabled))
        return action

    def _selected(self, title: str) -> str | None:
        """El producto seleccionado, o un aviso: una acción que no hace nada al
        pulsarla sin selección es feedback invisible (re-auditoría POS)."""
        product_id = self.table.selected_row_id()
        if not product_id:
            MessageDialog.information(self, title, "Selecciona un producto del catálogo.")
        return product_id

    def _edit_selected(self) -> None:
        product_id = self._selected("Editar")
        if product_id:
            self._open_form(product_id)

    # ── ciclo de vida (§6.3/§6.4) ─────────────────────────────────────────────
    def _submit_selected(self) -> None:
        product_id = self._selected("Enviar a revisión")
        if not product_id:
            return
        ok, message = self._presenter.submit_product(product_id)
        self._notify(ok, message, "Enviar a revisión")
        if ok:
            self.refresh(query=self.search.text() or None)
            self._emit_changed()

    def _activate_selected(self) -> None:
        product_id = self._selected("Activar")
        if not product_id:
            return
        # §6.4: preparación para activación — mostrar faltantes antes de activar.
        readiness = self._presenter.activation_readiness(product_id)
        if readiness is not None and not readiness.ready:
            faltantes = "\n".join(f"• {m}" for m in readiness.missing)
            MessageDialog.information(
                self, "Preparación para activación",
                "No se puede activar todavía. Faltan datos:\n\n" + faltantes)
            return
        ok, message = self._presenter.activate_product(product_id)
        self._notify(ok, message, "Activar")
        if ok:
            self.refresh(query=self.search.text() or None)
            self._emit_changed()

    def _notify(self, ok: bool, message: str, title: str) -> None:
        if ok:
            MessageDialog.information(self, title, message or "Operación realizada.")
        else:
            MessageDialog.warning(self, title, message or "No se pudo completar.")

    def _open_variants(self) -> None:
        product_id = self._selected("Variantes")
        if not product_id:
            return
        from frontend.desktop.modules.products.dialogs.variant_generator_dialog import (
            VariantGeneratorDialog,
        )
        row = self._presenter.get_product(product_id) or {}
        VariantGeneratorDialog(self._presenter, product_id=product_id,
                               product_name=row.get("name") or "Producto",
                               parent=self).exec_()
        self.refresh(query=self.search.text() or None)

    def _open_recipes(self) -> None:
        product_id = self._selected("Recetas")
        if not product_id:
            return
        from frontend.desktop.modules.products.dialogs.recipes_dialog import (
            RecipesDialog,
        )
        row = self._presenter.get_product(product_id) or {}
        RecipesDialog(self._presenter, product_id=product_id,
                      product_name=row.get("name") or "Producto",
                      parent=self).exec_()

    def _open_yields(self) -> None:
        product_id = self._selected("Rendimientos")
        if not product_id:
            return
        from frontend.desktop.modules.products.dialogs.yields_dialog import (
            YieldProfilesDialog,
        )
        row = self._presenter.get_product(product_id) or {}
        YieldProfilesDialog(self._presenter, product_id=product_id,
                            product_name=row.get("name") or "Producto",
                            parent=self).exec_()

    def _open_cutting(self) -> None:
        product_id = self._selected("Despiece")
        if not product_id:
            return
        from frontend.desktop.modules.products.dialogs.cutting_dialog import (
            CuttingSchemesDialog,
        )
        row = self._presenter.get_product(product_id) or {}
        CuttingSchemesDialog(self._presenter, product_id=product_id,
                             product_name=row.get("name") or "Producto",
                             species_id=row.get("species_id") or "",
                             parent=self).exec_()

    def _open_bundles(self) -> None:
        product_id = self._selected("Combos")
        if not product_id:
            return
        from frontend.desktop.modules.products.dialogs.bundles_dialog import (
            BundlesDialog,
        )
        row = self._presenter.get_product(product_id) or {}
        BundlesDialog(self._presenter, product_id=product_id,
                      product_name=row.get("name") or "Producto",
                      parent=self).exec_()

    def _open_images(self) -> None:
        product_id = self._selected("Imágenes")
        if not product_id:
            return
        from frontend.desktop.modules.products.dialogs.image_gallery_dialog import (
            ImageGalleryDialog,
        )
        row = self._presenter.get_product(product_id) or {}
        ImageGalleryDialog(self._presenter, product_id=product_id,
                           product_name=row.get("name") or "Producto",
                           parent=self).exec_()

    def _open_barcodes(self) -> None:
        product_id = self._selected("Códigos de barras")
        if not product_id:
            return
        from frontend.desktop.modules.products.dialogs.barcodes_dialog import BarcodesDialog
        row = self._presenter.get_product(product_id) or {}
        BarcodesDialog(self._presenter.codes_profiles, product_id=product_id,
                       product_name=row.get("name") or "Producto", parent=self).exec_()

    def _open_profiles(self) -> None:
        product_id = self._selected("Calidad, vida útil y logística")
        if not product_id:
            return
        from frontend.desktop.modules.products.dialogs.profiles_dialog import ProfilesDialog
        row = self._presenter.get_product(product_id) or {}
        ProfilesDialog(self._presenter.codes_profiles, product_id=product_id,
                       product_name=row.get("name") or "Producto", parent=self).exec_()

    def _open_meat(self) -> None:
        product_id = self._selected("Clasificación cárnica y peso variable")
        if not product_id:
            return
        from frontend.desktop.modules.products.dialogs.meat_product_dialog import (
            MeatProductDialog,
        )
        row = self._presenter.get_product(product_id) or {}
        MeatProductDialog(self._presenter.meat, product_id=product_id,
                          product_name=row.get("name") or "Producto", parent=self).exec_()

    def _open_purchase_units(self) -> None:
        product_id = self._selected("Unidades de compra")
        if not product_id:
            return
        from frontend.desktop.modules.products.dialogs.purchase_units_dialog import (
            PurchaseUnitsDialog,
        )
        row = self._presenter.get_product(product_id) or {}
        PurchaseUnitsDialog(self._presenter, product_id=product_id,
                            product_name=row.get("name") or "Producto",
                            parent=self).exec_()

    def _open_form(self, product_id) -> None:
        from frontend.desktop.modules.products.dialogs.product_form_dialog import (
            ProductFormDialog,
        )
        dialog = ProductFormDialog(self._presenter, product_id=product_id, parent=self)
        if dialog.exec_():
            self.refresh(query=self.search.text() or None)
            self._emit_changed()

    def refresh(self, *, query=None) -> None:
        family = self.family.currentData() if hasattr(self, "family") else None
        table = self._presenter.catalog(query=query, family=family or None)
        self.table.load_rows(table.rows, row_ids=table.row_ids)
