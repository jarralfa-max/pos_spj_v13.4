"""Audit page (INV-25 / §20.3) — recent inventory audit trail.

Presentation-only: lists recent audit entries (date, entity, action, user,
authorizer) for the branch. All values come from the presenter; no SQL, no
business logic. Revisiting the section re-reads the audit log.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class AuditPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryAuditPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Auditoría",
            subtitle="Bitácora de operaciones y autorizaciones de inventario.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Fecha", "text"),
            ColumnSpec("Entidad", "text"),
            ColumnSpec("Acción", "text"),
            ColumnSpec("Usuario", "text"),
            ColumnSpec("Autorizó", "text"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.audit()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
