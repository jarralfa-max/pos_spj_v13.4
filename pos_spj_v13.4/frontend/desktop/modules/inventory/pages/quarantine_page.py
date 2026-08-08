"""Quarantine page (INV-25 / §31) — open quarantines + release/dispose (P0-B).

Lists open quarantines (product, lot, reason, quantity, status) for the
branch and lets the user act on the selected row: liberar (release, stock
returns to AVAILABLE) or disponer (dispose, permanent issue — irreversible).
All values and mutations go through the presenter, which calls the real
authorized use cases; this page has no SQL and no business logic — it only
confirms intent and shows the result.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    StandardTable,
    create_danger_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import ConfirmationDialog
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing
from frontend.desktop.modules.inventory.dialogs import DisposeQuarantineDialog


class QuarantinePage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryQuarantinePage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Cuarentena",
            subtitle="Cuarentenas abiertas: bloqueo, revisión y liberación de lotes.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.release_button = create_secondary_button(text="Liberar")
        self.release_button.clicked.connect(self._on_release)
        actions.addWidget(self.release_button)
        self.dispose_button = create_danger_button(text="Disponer")
        self.dispose_button.clicked.connect(self._on_dispose)
        actions.addWidget(self.dispose_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Producto", "text"),
            ColumnSpec("Lote", "text"),
            ColumnSpec("Motivo", "text"),
            ColumnSpec("Cantidad", "numeric"),
            ColumnSpec("Estado", "status"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.quarantines()
        self._table.load_rows(table.rows, row_ids=table.row_ids)

    def _selected_quarantine_id(self) -> str | None:
        qid = self._table.selected_row_id()
        if not qid:
            QMessageBox.information(
                self, "Cuarentena", "Selecciona una cuarentena de la lista.")
            return None
        return qid

    def _on_release(self) -> None:
        qid = self._selected_quarantine_id()
        if qid is None:
            return
        dlg = ConfirmationDialog(
            self, title="Liberar cuarentena",
            message="El stock volverá a estar disponible. ¿Continuar?",
            confirm_text="Liberar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.release_quarantine(quarantine_id=qid)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Cuarentena", message)
        if ok:
            self.refresh()

    def _on_dispose(self) -> None:
        qid = self._selected_quarantine_id()
        if qid is None:
            return
        dlg = DisposeQuarantineDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.dispose_quarantine(
            quarantine_id=qid, reason=dlg.reason())
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Cuarentena", message)
        if ok:
            self.refresh()
