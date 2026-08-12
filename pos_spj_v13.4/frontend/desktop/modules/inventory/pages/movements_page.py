"""Movements page (INV-6 / §15) — ledger movements + detail/reverso.

Lists the most recent posted movements (date, type, source module/document,
status) for the branch and lets the user drill into one via "Ver detalle":
header, lines, sibling movements sharing the same source document, and the
audit trail (who posted it, who reversed it). Reversing only happens from
inside that detail view — you must look at what you're reversing first — and
is gated by the session's ``movement_reverse`` capability (the backend
re-validates independently; hiding the button is UX, not security). All
values come from the presenter; no SQL, no business logic here.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    StandardTable,
    create_secondary_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.inventory.dialogs import MovementDetailDialog
from frontend.desktop.themes.tokens import Spacing


class MovementsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryMovementsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Movimientos",
            subtitle="Ledger de movimientos: entradas, salidas y transferencias.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.detail_button = create_secondary_button(text="Ver detalle")
        self.detail_button.clicked.connect(self._on_detail)
        actions.addWidget(self.detail_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Fecha", "text"),
            ColumnSpec("Tipo", "text"),
            ColumnSpec("Módulo", "text"),
            ColumnSpec("Documento", "text"),
            ColumnSpec("Estado", "status"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.movements()
        self._table.load_rows(table.rows, row_ids=table.row_ids)

    def _selected_movement_id(self) -> str | None:
        mid = self._table.selected_row_id()
        if not mid:
            QMessageBox.information(
                self, "Movimientos", "Selecciona un movimiento de la lista.")
            return None
        return mid

    def _on_detail(self) -> None:
        mid = self._selected_movement_id()
        if mid is None:
            return
        header = self._presenter.movement_detail(movement_id=mid)
        if header is None:
            QMessageBox.warning(self, "Movimientos", "Movimiento no encontrado.")
            return
        caps = self._presenter.capabilities()

        def reverse(reason: str) -> None:
            ok, message, _ = self._presenter.reverse_movement(
                movement_id=mid, reason=reason)
            (QMessageBox.information if ok else QMessageBox.warning)(
                self, "Movimientos", message)
            if ok:
                dlg.accept()
                self.refresh()

        dlg = MovementDetailDialog(
            self, header=header,
            lines=self._presenter.movement_lines(movement_id=mid),
            source_document=self._presenter.movement_source_document(movement_id=mid),
            audit=self._presenter.movement_audit(movement_id=mid),
            can_reverse=caps.movement_reverse, reverse=reverse)
        dlg.exec_()
