"""Transfers page (INV-25 / §24) — recent physical transfers for the branch.

Presentation-only: lists recent transfers (folio, type, origin, destination,
status, updated) that touch the branch. It is a read-only window into the
Transfers bounded context; the full lifecycle (request → dispatch → receipt) is
managed in the dedicated Transferencias module. All values come from the
presenter; no SQL, no business logic. Revisiting the section re-reads the list.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class TransfersPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryTransfersPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Transferencias",
            subtitle="Movimiento de existencias entre sucursales y almacenes "
                     "(sólo lectura; se gestionan en el módulo de Transferencias).",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Folio", "text"),
            ColumnSpec("Tipo", "text"),
            ColumnSpec("Origen", "text"),
            ColumnSpec("Destino", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Actualizado", "text"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.transfers()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
