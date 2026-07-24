"""Canonical responsive Transfers page shell using only SPJ Design System."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_primary_button
from frontend.desktop.components.cards import SectionCard
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.search_input import SearchInput
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.themes.tokens import Spacing


class TransferWorkspacePage(QWidget):
    page_id = ""
    title = "Transferencias"
    subtitle = "Operación logística interna"
    action_text = "Nueva solicitud"

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._loaded = False
        self.setObjectName("transfersPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)
        action = create_primary_button(self, self.action_text)
        action.setVisible(bool(self.action_text))
        root.addWidget(PageHeader(self, title=self.title, subtitle=self.subtitle,
                                  actions=[action] if self.action_text else []))
        self.search = SearchInput(self, placeholder="Buscar folio, origen o destino…")
        self.search.setAccessibleName(f"Buscar en {self.title}")
        self.search.search_changed.connect(self.reload)
        root.addWidget(self.search)
        card = SectionCard(self, title="Operaciones")
        self.table = StandardTable([
            ColumnSpec("Folio"), ColumnSpec("Origen"), ColumnSpec("Destino"),
            ColumnSpec("Estado", "status"), ColumnSpec("Actualización", "date"),
        ], card)
        self.table.setAccessibleName(f"Listado de {self.title}")
        self.table.setFocusPolicy(Qt.StrongFocus)
        card.add(self.table)
        self.empty_label = QLabel("", card)
        self.empty_label.setObjectName("emptyStateMessage")
        self.empty_label.setWordWrap(True)
        card.add(self.empty_label)
        root.addWidget(card, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload("")

    def reload(self, search: str = "") -> None:
        model = self._presenter.load_page(self.page_id, search)
        rows = [[row.reference, row.origin, row.destination, row.status,
                 row.updated_at] for row in model.rows]
        self.table.load_rows(rows, row_ids=[row.entity_id for row in model.rows])
        self.empty_label.setText(model.empty_message if not rows else "")
        self.empty_label.setVisible(not rows)
        self._loaded = True
