"""Centro de notificaciones: historial personal sobre la bandeja canónica."""

from __future__ import annotations

from PyQt5.QtWidgets import QCheckBox, QDialogButtonBox, QLabel

from frontend.desktop.components import ColumnSpec, SearchInput, StandardTable
from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.dialogs import StandardDialog


class NotificationCenterDialog(StandardDialog):
    def __init__(self, inbox_service, user_id: str, parent=None) -> None:
        super().__init__(parent, title="Centro de notificaciones", width=760)
        self._inbox = inbox_service
        self._user_id = user_id
        self.setObjectName("notificationCenterDialog")
        body = self.content_layout()
        self.search = SearchInput(self, placeholder="Buscar avisos…")
        self.search.search_changed.connect(lambda _q: self.refresh())
        body.addWidget(self.search)
        self.unread_only = QCheckBox("Solo no leídas", self)
        self.unread_only.toggled.connect(lambda _on: self.refresh())
        body.addWidget(self.unread_only)
        self.table = StandardTable(columns=[
            ColumnSpec("Fecha", "date"), ColumnSpec("Estado", "status"),
            ColumnSpec("Tipo", "text"), ColumnSpec("Sucursal", "text"),
            ColumnSpec("Aviso", "text", min_width=230, preferred_width=280,
                       stretch=True)])
        body.addWidget(self.table)
        self.detail = QLabel("Selecciona un aviso para leerlo completo.", self)
        self.detail.setWordWrap(True)
        body.addWidget(self.detail)
        self.table.itemSelectionChanged.connect(self._show_selected)
        read_button = create_secondary_button(self, "Marcar como leído")
        read_button.clicked.connect(self._mark_selected)
        body.addWidget(read_button)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        self.add_footer_widget(buttons)
        self.refresh()

    def refresh(self) -> None:
        rows = self._inbox.history(self._user_id,
                                   unread_only=self.unread_only.isChecked())
        q = self.search.query().casefold()
        self._rows = {row.id: row for row in rows if q in (
            f"{row.title} {row.body} {row.kind} {row.branch_id or ''}").casefold()}
        self.table.load_rows([
            [row.created_at[:16].replace("T", " "),
             "Leída" if row.read else "Nueva", row.kind, row.branch_id or "Global",
             row.title] for row in self._rows.values()], row_ids=list(self._rows))

    def _show_selected(self) -> None:
        row = self._rows.get(self.table.selected_row_id())
        self.detail.setText(row.body if row is not None else
                            "Selecciona un aviso para leerlo completo.")

    def _mark_selected(self) -> None:
        notification_id = self.table.selected_row_id()
        if notification_id:
            self._inbox.mark_read(self._user_id, notification_id)
            self.refresh()
