"""Product prices page (PRC-7) — sale price by product / branch / list.

UI only: búsqueda, tabla y acciones. El precio mínimo, la inmutabilidad de una
lista aprobada y la autorización para vender bajo el mínimo las decide el caso
de uso, no esta pantalla.

Cuando el precio pertenece a una lista de solo lectura, la pantalla no se
limita a negarse: ofrece el único camino que el dominio permite —duplicar la
lista— y abre el precio ya sobre la copia en borrador.
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
    DuplicatePriceListDialog,
    ProductPriceFormDialog,
    VolumeTierDialog,
)
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
            ColumnSpec("Estado de la lista", "list_status"),
            ColumnSpec("Vigencia", "validity"),
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

    def _ask(self, message: str) -> bool:
        respuesta = QMessageBox.question(
            self, "Precios", message, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        return respuesta == QMessageBox.Yes

    def _price_dialog(self, *, initial=None):
        """El diálogo de precio con las listas editables RECIÉN leídas (una
        copia creada hace un instante debe aparecer)."""
        return ProductPriceFormDialog(
            self, list_options=self._presenter.price_list_options(),
            product_provider=getattr(self._presenter, "product_options", None),
            empty_reason_provider=getattr(self._presenter, "product_search_reason", None),
            branch_options=self._presenter.branch_options(), initial=initial)

    def _save_from(self, dialog) -> None:
        if not dialog.exec_():
            return
        ok, msg, _ = self._presenter.set_product_price(**dialog.values())
        self._notify(ok, msg)

    def _duplicate(self, *, list_id: str, label: str, code: str,
                   name: str = "") -> str | None:
        """Duplica una lista de solo lectura y devuelve el id del borrador."""
        dialog = DuplicatePriceListDialog(
            self, source_label=label,
            initial_code=self._presenter.suggest_copy_code(code),
            initial_name=f"{name or code} (copia)")
        if not dialog.exec_():
            return None
        ok, msg, datos = self._presenter.duplicate_price_list(
            source_list_id=list_id, **dialog.values())
        if not ok:
            self._notify(False, msg)
            return None
        QMessageBox.information(self, "Precios", msg)
        self.refresh()
        return datos.get("entity_id")

    def _offer_duplicate_for_capture(self, state) -> None:
        """Sin listas editables: explica y, si hay una lista vigente que se
        pueda duplicar, ofrece hacerlo y abrir la captura sobre la copia."""
        mensaje = self._presenter.no_editable_lists_message(state)
        candidatas = [l for l in state.read_only if l["status"] in ("ACTIVE", "APPROVED")]
        if not candidatas or not self._can(PricingPermissions.LIST_CREATE):
            self._notify(False, mensaje)
            return
        origen = next((l for l in candidatas if l["status"] == "ACTIVE"), candidatas[0])
        if not self._ask(f"{mensaje}\n\n¿Duplicar ahora «{origen['label']}»?"):
            return
        codigo, _, nombre = origen["label"].partition(" · ")
        nueva = self._duplicate(list_id=origen["id"], label=origen["label"],
                                code=codigo, name=nombre)
        if nueva:
            self._save_from(self._price_dialog(initial={"price_list_id": nueva}))

    # ── acciones ─────────────────────────────────────────────────────────
    def _create(self) -> None:
        state = self._presenter.price_list_capture_state()
        if not state.editable:
            self._offer_duplicate_for_capture(state)
            return
        self._save_from(self._price_dialog())

    def _edit(self) -> None:
        price_id = self.table.selected_row_id()
        if not price_id:
            self._notify(False, "Elige un precio de la tabla.")
            return
        datos = self._presenter.price_details(price_id)
        if not datos:
            self._notify(False, "No se pudo cargar el precio elegido.")
            return
        motivo = self._presenter.read_only_list_message(datos)
        if motivo is None:
            self._save_from(self._price_dialog(initial=datos))
            return
        # Lista de solo lectura: decir POR QUÉ y ofrecer la salida (duplicar),
        # salvo que el estado guardado no se reconozca — eso es un dato que
        # corregir, no una lista que copiar.
        duplicable = (self._presenter.price_list_summary(datos["price_list_id"]) or {}
                      ).get("status_recognized", False)
        if not duplicable or not self._can(PricingPermissions.LIST_CREATE):
            self._notify(False, motivo)
            return
        if not self._ask(f"{motivo}\n\n¿Duplicar la lista ahora y editar este precio "
                         "en la copia?"):
            return
        nueva = self._duplicate(
            list_id=datos["price_list_id"],
            label=f"{datos.get('list_code') or ''} · {datos.get('list_name') or ''}",
            code=datos.get("list_code") or "", name=datos.get("list_name") or "")
        if nueva:
            # Upsert por (lista, producto, sucursal): guardar sobre la copia
            # reescribe el precio copiado, no crea otro.
            self._save_from(self._price_dialog(initial={**datos, "price_list_id": nueva}))

    def _apply_bulk(self) -> None:
        state = self._presenter.price_list_capture_state()
        if not state.editable:
            self._notify(False, self._presenter.no_editable_lists_message(state))
            return
        categorias = self._presenter.category_options()
        if not categorias:
            self._notify(False, "No hay categorías de producto activas a las que "
                                "aplicar un precio en lote.")
            return
        dialog = BulkPriceDialog(self, list_options=list(state.editable),
                                 category_options=categorias,
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
        datos = self._presenter.price_details(product_price_id) or {}
        motivo = self._presenter.read_only_list_message(datos) if datos else None
        if motivo:
            self._notify(False, motivo)
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
