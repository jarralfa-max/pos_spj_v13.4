"""Auditoría de Productos — quién cambió qué, cuándo y por qué (§40, PROD-22).

UI only: filtros (texto y acción), tabla de movimientos y el detalle antes/después
del renglón elegido. Lee por el presenter de auditoría; nunca escribe.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import ColumnSpec, PageHeader, SearchInput, StandardTable
from frontend.desktop.components.cards import SectionCard
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.components.text_inputs import StandardTextArea
from frontend.desktop.themes.tokens import Spacing


class ProductAuditPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productAuditPage")
        self._audit = getattr(presenter, "audit", None)
        self._rows: list[dict] = []

        # Desbordamiento explícito (design system): a 1366×768 la página hace
        # scroll en lugar de recortar controles.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.viewport = PageViewport(self)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        layout.addWidget(PageHeader(
            title="Auditoría de productos",
            subtitle="Quién cambió cada dato del maestro, cuándo y qué cambió.",
            icon=getattr(Icons, "AUDIT", None), compact=True))

        filters = QHBoxLayout()
        self.search = SearchInput(placeholder="Producto, código o usuario…")
        self.search.textChanged.connect(lambda _t: self.refresh())
        self.action = QComboBox()
        self.action.setAccessibleName("Acción")
        self.action.currentIndexChanged.connect(lambda _i: self.refresh())
        filters.addWidget(self.search, 1)
        filters.addWidget(self.action)
        layout.addLayout(filters)

        self.table = StandardTable(columns=[
            ColumnSpec("Fecha", "date"), ColumnSpec("Acción", "text"),
            ColumnSpec("Producto / registro", "text"), ColumnSpec("Usuario", "text"),
            ColumnSpec("Cambio", "text"), ColumnSpec("Motivo", "text")])
        self.table.itemSelectionChanged.connect(self._show_detail)
        layout.addWidget(self.table, 2)

        detail = SectionCard(self, title="Detalle (antes / después)")
        self.detail = StandardTextArea()
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(150)
        detail.add(self.detail)
        layout.addWidget(detail, 1)

        self.empty = QLabel("")
        self.empty.setProperty("role", "muted")
        layout.addWidget(self.empty)
        self.viewport.set_page(body)
        outer.addWidget(self.viewport)
        self._load_actions()
        self.refresh()

    def _load_actions(self) -> None:
        self.action.blockSignals(True)
        self.action.clear()
        self.action.addItem("Todas las acciones", "")
        for value, label in (self._audit.action_options() if self._audit else []):
            self.action.addItem(label, value)
        self.action.blockSignals(False)

    def refresh(self) -> None:
        if self._audit is None or not self._audit.can_view:
            self.table.load_rows([], row_ids=[])
            self.empty.setText("No tienes permiso para consultar la auditoría de productos.")
            return
        self._rows = self._audit.entries(text=self.search.text() or None,
                                         action=self.action.currentData() or None)
        self.table.load_rows(
            [[(r["occurred_at"] or "")[:19].replace("T", " "), r["action_label"],
              r["subject"], r["user_name"] or "", r["change"][:120], r["reason"] or ""]
             for r in self._rows],
            row_ids=[r["id"] for r in self._rows])
        self.empty.setText("" if self._rows else "Sin movimientos para este filtro.")
        self.detail.setPlainText("")

    def _show_detail(self) -> None:
        entry_id = self.table.selected_row_id()
        row = next((r for r in self._rows if r["id"] == entry_id), None)
        self.detail.setPlainText(row["detail"] if row else "")
