"""Price lists page (PRC-7) — base/channel/customer/promotional lists + status.

UI only: tabla + acciones de ciclo de vida. Sin SQL ni reglas de negocio — cada
botón ordena una operación al presentador, que llama al caso de uso; es el caso
de uso quien valida permiso, estado y segregación de funciones.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from backend.application.pricing.permissions import PricingPermissions
from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    StandardTable,
    create_primary_button,
    create_secondary_button,
    create_success_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.pricing.dialogs import (
    DuplicatePriceListDialog,
    PriceListFormDialog,
)
from frontend.desktop.themes.tokens import Spacing


class PriceListsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("priceListsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Listas de Precio",
            subtitle="Listas base, de canal, de cliente y promocionales.",
            icon=getattr(Icons, "CATALOG", None), compact=True)
        nueva = create_primary_button(self, "Nueva lista")
        nueva.clicked.connect(self._create)
        nueva.setEnabled(self._can(PricingPermissions.LIST_CREATE))
        self.header.add_action(nueva)
        layout.addWidget(self.header)

        self.table = StandardTable(columns=[
            ColumnSpec("Código", "code"),
            ColumnSpec("Nombre", "name"),
            ColumnSpec("Tipo", "kind"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Descuento", "discount"),
        ])
        layout.addWidget(self.table, 1)

        # El ciclo de vida completo. Antes esta pantalla era una tabla sin una
        # sola acción: el módulo se abría y no se podía ejecutar nada.
        acciones = QHBoxLayout()
        acciones.setSpacing(Spacing.SM)
        self._botones = {}
        for clave, etiqueta, permiso, constructor in (
            ("submit", "Enviar a revisión", PricingPermissions.LIST_SUBMIT,
             create_secondary_button),
            ("approve", "Aprobar", PricingPermissions.LIST_APPROVE, create_success_button),
            ("activate", "Activar", PricingPermissions.LIST_ACTIVATE, create_success_button),
            ("deactivate", "Desactivar", PricingPermissions.LIST_DEACTIVATE,
             create_secondary_button),
        ):
            boton = constructor(self, etiqueta)
            boton.setEnabled(self._can(permiso))
            boton.clicked.connect(lambda _=False, k=clave: self._transition(k))
            acciones.addWidget(boton)
            self._botones[clave] = boton
        # Duplicar no es una transición: es la única forma de partir de una
        # lista APROBADA o ACTIVA, que el dominio declara inmutable.
        self._duplicar = create_secondary_button(self, "Duplicar")
        self._duplicar.clicked.connect(self._duplicate)
        self._duplicar.setEnabled(self._can(PricingPermissions.LIST_CREATE))
        acciones.addWidget(self._duplicar)
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

    def _selected(self) -> str | None:
        return self.table.selected_row_id()

    # ── acciones ─────────────────────────────────────────────────────────
    def _create(self) -> None:
        dialog = PriceListFormDialog(self)
        if not dialog.exec_():
            return
        ok, msg, _ = self._presenter.create_price_list(**dialog.values())
        self._notify(ok, msg)

    def _duplicate(self) -> None:
        price_list_id = self._selected()
        if not price_list_id:
            self._notify(False, "Elige una lista de precios.")
            return
        dialog = DuplicatePriceListDialog(self)
        if not dialog.exec_():
            return
        ok, msg, _ = self._presenter.duplicate_price_list(
            source_list_id=price_list_id, **dialog.values())
        self._notify(ok, msg)

    def _transition(self, key: str) -> None:
        price_list_id = self._selected()
        if not price_list_id:
            self._notify(False, "Selecciona una lista de precios.")
            return
        operacion = {
            "submit": self._presenter.submit_price_list,
            "approve": self._presenter.approve_price_list,
            "activate": self._presenter.activate_price_list,
            "deactivate": self._presenter.deactivate_price_list,
        }[key]
        ok, msg, _ = operacion(price_list_id)
        self._notify(ok, msg)

    def refresh(self) -> None:
        vm = self._presenter.price_lists()
        self.table.load_rows(vm.rows, row_ids=vm.row_ids)
