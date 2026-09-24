"""Product prices page (PRC-7) — sale price by product / branch / list.

UI only: búsqueda, tabla y acciones. El precio mínimo, la inmutabilidad de una
lista aprobada y la autorización para vender bajo el mínimo las decide el caso
de uso, no esta pantalla.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from backend.application.pricing.permissions import PricingPermissions
from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    SearchInput,
    StandardTable,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.pricing.dialogs import (
    BulkPriceDialog,
    ProductPriceFormDialog,
    VolumeTierDialog,
)
from frontend.desktop.modules.pricing.view_models import list_status_es
from frontend.desktop.themes.tokens import Spacing


class ProductPricesPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productPricesPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Precios por Producto",
            subtitle="Precio de venta por producto, sucursal y lista; precio mínimo.",
            icon=getattr(Icons, "PRICE", None), compact=True)
        nuevo = create_primary_button(self, "Nuevo precio")
        nuevo.clicked.connect(self._create)
        nuevo.setEnabled(self._can(PricingPermissions.PRICE_CREATE))
        self.header.add_action(nuevo)
        layout.addWidget(self.header)

        self.search = SearchInput(placeholder="Buscar producto por nombre o código…")
        self.search.textChanged.connect(self._on_search)
        layout.addWidget(self.search)

        self.table = StandardTable(columns=[
            ColumnSpec("Producto", "product"),
            ColumnSpec("Lista", "list"),
            ColumnSpec("Sucursal", "branch"),
            ColumnSpec("Precio", "sale_price"),
            ColumnSpec("Mínimo", "min_price"),
        ])
        layout.addWidget(self.table, 1)

        acciones = QHBoxLayout()
        acciones.setSpacing(Spacing.SM)
        self._editar = create_secondary_button(self, "Editar precio")
        self._editar.clicked.connect(self._edit)
        self._editar.setEnabled(self._can(PricingPermissions.PRICE_EDIT))
        acciones.addWidget(self._editar)
        self._lote = create_secondary_button(self, "Aplicar en lote")
        self._lote.clicked.connect(self._apply_bulk)
        self._lote.setEnabled(self._can(PricingPermissions.PRICE_EDIT))
        acciones.addWidget(self._lote)
        self._volumen = create_secondary_button(self, "Escala por volumen")
        self._volumen.clicked.connect(self._add_volume_tier)
        self._volumen.setEnabled(self._can(PricingPermissions.VOLUME_PRICE_MANAGE))
        acciones.addWidget(self._volumen)
        acciones.addStretch(1)
        layout.addLayout(acciones)

        self.refresh()

    # ── helpers ──────────────────────────────────────────────────────────
    def _can(self, permission_code: str) -> bool:
        checker = getattr(self._presenter, "can", None)
        return bool(callable(checker) and checker(permission_code))

    def _notify(self, ok: bool, message: str) -> None:
        if ok:
            QMessageBox.information(self, "Precios", message)
            self.refresh()
        else:
            QMessageBox.warning(self, "Precios", message)

    # ── acciones ─────────────────────────────────────────────────────────
    def _create(self) -> None:
        listas = self._presenter.price_list_options()
        if not listas:
            self._notify(False, "No hay listas editables: crea una, o usa una "
                                "en borrador o en revisión.")
            return
        dialog = ProductPriceFormDialog(
            self, list_options=listas,
            product_provider=getattr(self._presenter, "product_options", None),
            empty_reason_provider=getattr(self._presenter, "product_search_reason", None),
            branch_options=self._presenter.branch_options())
        if not dialog.exec_():
            return
        ok, msg, _ = self._presenter.set_product_price(**dialog.values())
        self._notify(ok, msg)

    def _edit(self) -> None:
        price_id = self.table.selected_row_id()
        if not price_id:
            self._notify(False, "Elige un precio de la tabla.")
            return
        datos = self._presenter.price_details(price_id)
        if not datos:
            self._notify(False, "No se pudo cargar el precio elegido.")
            return
        listas = self._presenter.price_list_options()
        if datos.get("price_list_id") not in {clave for clave, _ in listas}:
            # Decir POR QUÉ, en vez de abrir un formulario que no puede guardar:
            # una lista aprobada o activa es inmutable por regla de dominio.
            estado = list_status_es(datos.get("list_status"))
            self._notify(False,
                         f"La lista «{datos.get('list_name') or ''}» está "
                         f"{estado} y es inmutable. Duplícala para cambiar sus precios.")
            return
        dialog = ProductPriceFormDialog(
            self, list_options=listas,
            product_provider=getattr(self._presenter, "product_options", None),
            empty_reason_provider=getattr(self._presenter, "product_search_reason", None),
            branch_options=self._presenter.branch_options(), initial=datos)
        if not dialog.exec_():
            return
        ok, msg, _ = self._presenter.set_product_price(**dialog.values())
        self._notify(ok, msg)

    def _apply_bulk(self) -> None:
        listas = self._presenter.price_list_options()
        if not listas:
            self._notify(False, "No hay listas editables: crea una, o usa una "
                                "en borrador o en revisión.")
            return
        categorias = self._presenter.category_options()
        if not categorias:
            self._notify(False, "No hay categorías de producto activas a las que "
                                "aplicar un precio en lote.")
            return
        dialog = BulkPriceDialog(self, list_options=listas, category_options=categorias,
                                 branch_options=self._presenter.branch_options())
        if not dialog.exec_():
            return
        ok, msg, _ = self._presenter.apply_price_in_bulk(**dialog.values())
        self._notify(ok, msg)

    def _add_volume_tier(self) -> None:
        product_price_id = self.table.selected_row_id()
        if not product_price_id:
            self._notify(False, "Selecciona un precio de la tabla.")
            return
        dialog = VolumeTierDialog(self)
        if not dialog.exec_():
            return
        ok, msg, _ = self._presenter.set_volume_price(
            product_price_id=product_price_id, **dialog.values())
        self._notify(ok, msg)

    def _on_search(self, text) -> None:
        self.refresh(query=text)

    def refresh(self, *, query=None) -> None:
        vm = self._presenter.product_prices(query=query)
        self.table.load_rows(vm.rows, row_ids=vm.row_ids)
