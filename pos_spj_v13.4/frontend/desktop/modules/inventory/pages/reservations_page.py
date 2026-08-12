"""Reservations page (INV-25 / §22) — a product's active reservations +
crear/asignar/liberar.

An ``EntitySearchInput`` resolves the product by name, code or barcode against
the canonical catalog (§P0-D — never a hand-typed UUID); the page lists its
active reservations (source, document, warehouse, quantity, status) and lets
an authorized user create a new reservation for the selected product, assign
a selected reservation to lots by FEFO ("Asignar"), or release it. All actions
are gated by the session's resolved capabilities (§17) — the backend
re-validates every one independently. All values come from the presenter; no
SQL, no business logic.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    StandardTable,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import ConfirmationDialog
from frontend.desktop.components.entity_search_input import EntitySearchInput
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.inventory.dialogs import (
    CreateReservationDialog,
    ReleaseReservationDialog,
)
from frontend.desktop.themes.tokens import Spacing


class ReservationsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryReservationsPage")
        self._presenter = presenter
        self._product_id = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Reservas",
            subtitle="Reservas activas por producto: origen, documento y estado.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._search = EntitySearchInput(
            self, provider=self._presenter.product_options,
            placeholder="Buscar producto por nombre, código o código de barras…")
        self._search.selected.connect(self._on_product_selected)
        layout.addWidget(self._search)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.create_button = create_primary_button(text="Nueva reserva")
        self.create_button.clicked.connect(self._on_create)
        actions.addWidget(self.create_button)
        self.allocate_button = create_secondary_button(text="Asignar")
        self.allocate_button.clicked.connect(self._on_allocate)
        actions.addWidget(self.allocate_button)
        self.release_button = create_secondary_button(text="Liberar")
        self.release_button.clicked.connect(self._on_release)
        actions.addWidget(self.release_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Origen", "text"),
            ColumnSpec("Documento", "text"),
            ColumnSpec("Almacén", "text"),
            ColumnSpec("Cantidad", "numeric"),
            ColumnSpec("Estado", "status"),
        ])
        layout.addWidget(self._table)

    def _on_product_selected(self, product_id) -> None:
        self._product_id = str(product_id or "")
        self.refresh()

    def refresh(self) -> None:
        table = self._presenter.reservations(product_id=self._product_id)
        self._table.load_rows(table.rows, row_ids=table.row_ids)
        caps = self._presenter.capabilities()
        self.create_button.setVisible(caps.reservation_create)
        self.allocate_button.setVisible(caps.reservation_create)
        self.release_button.setVisible(caps.reservation_release)

    def _selected_reservation_id(self) -> str | None:
        rid = self._table.selected_row_id()
        if not rid:
            QMessageBox.information(
                self, "Reservas", "Selecciona una reserva de la lista.")
            return None
        return rid

    def _on_create(self) -> None:
        if not self._product_id:
            QMessageBox.information(self, "Reservas", "Selecciona un producto primero.")
            return
        dlg = CreateReservationDialog(
            self, warehouse_options=self._presenter.warehouse_options(),
            location_options=self._presenter.location_options())
        if dlg.exec_() != QDialog.Accepted:
            return
        quantity = dlg.quantity()
        if not quantity:
            QMessageBox.warning(self, "Reservas", "Captura una cantidad mayor a cero.")
            return
        ok, message, _ = self._presenter.create_reservation(
            product_id=self._product_id, source=dlg.source_code(),
            source_document_id=dlg.source_document_id(), quantity=quantity,
            weight=dlg.weight(), warehouse_id=dlg.warehouse_id(),
            location_id=dlg.location_id(), expires_at=dlg.expires_at())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Reservas", message)
        if ok:
            self.refresh()

    def _on_allocate(self) -> None:
        rid = self._selected_reservation_id()
        if rid is None:
            return
        dlg = ConfirmationDialog(
            self, title="Asignar reserva",
            message="Se asignarán lotes por FEFO a esta reserva. ¿Continuar?",
            confirm_text="Asignar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.allocate_reservation(reservation_id=rid)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Reservas", message)
        if ok:
            self.refresh()

    def _on_release(self) -> None:
        rid = self._selected_reservation_id()
        if rid is None:
            return
        dlg = ReleaseReservationDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.release_reservation(
            reservation_id=rid, reason=dlg.reason())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Reservas", message)
        if ok:
            self.refresh()
