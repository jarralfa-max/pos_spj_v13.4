"""Asientos contables — consulta y reverso controlado."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage
from frontend.desktop.components.buttons import create_danger_button


class JournalEntriesPage(FinancePage):
    title = "Asientos contables"
    subtitle = "Los asientos publicados son inmutables; toda corrección genera un reverso"
    # Auditoría F24: más de 200 asientos siguen accesibles (paginación del
    # servidor) y se encuentran por folio o descripción.
    searchable = True
    paginated = True
    columns = [
        ColumnSpec("Folio", "date"),
        ColumnSpec("Fecha", "date"),
        ColumnSpec("Descripción"),
        ColumnSpec("Diario", "status"),
        ColumnSpec("Total", "numeric"),
        ColumnSpec("Estado", "status"),
    ]

    def _build_actions(self) -> None:
        reverse_btn = create_danger_button(self, "Reversar asiento")
        reverse_btn.clicked.connect(self._reverse_selected)
        self.header.add_action(reverse_btn)

    def _reverse_selected(self) -> None:
        entry_id = self.table.selected_row_id()
        if not entry_id:
            self.notify(False, "Seleccione un asiento para reversar.")
            return
        from frontend.desktop.modules.finance.dialogs.reversal_dialog import ReversalDialog
        dialog = ReversalDialog(self)
        if dialog.exec_():
            self.notify(*self._presenter.reverse_entry(entry_id, dialog.reason()))

    def _load(self) -> None:
        search = self._search.query() if self.searchable else ""
        model = self._presenter.journal_entries(
            search=search, limit=self.page_size, offset=self._page * self.page_size)
        from frontend.desktop.modules.finance.finance_view_models import TableViewModel
        self.set_table(TableViewModel(model.rows, model.row_ids,
                                      total=self._presenter.journal_entries_count(search=search)))
