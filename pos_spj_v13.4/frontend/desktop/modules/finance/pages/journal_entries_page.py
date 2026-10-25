"""Asientos contables (§8.2–8.3): captura manual, validación, contabilización,
cancelación de borradores y reversión de contabilizados."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.dialogs.fields_dialog import ask_reason
from frontend.desktop.modules.finance.dialogs.journal_entry_dialog import JournalEntryDialog
from frontend.desktop.modules.finance.dialogs.table_dialog import TableDialog
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P

_STATUS = [("DRAFT", "Borrador"), ("VALIDATED", "Validado"), ("POSTED", "Contabilizado"),
           ("REVERSED", "Reversado"), ("CANCELLED", "Cancelado")]


class JournalEntriesPage(FinancePage):
    title = "Asientos"
    subtitle = "Pólizas de todos los módulos; las manuales nacen en borrador"
    searchable = True
    paginated = True
    period_filter = True
    status_filter = _STATUS
    columns = [
        ColumnSpec("Número", "date"),
        ColumnSpec("Fecha", "date"),
        ColumnSpec("Concepto"),
        ColumnSpec("Diario"),
        ColumnSpec("Origen", "status"),
        ColumnSpec("Total", "numeric"),
        ColumnSpec("Estado", "status"),
    ]
    header_actions = [("Nuevo asiento", P.JOURNAL_CREATE, "_create", True)]
    row_actions = [
        ("Ver detalle", P.JOURNAL_READ, "_detail"),
        ("Validar", P.JOURNAL_VALIDATE, "_validate"),
        ("Contabilizar", P.JOURNAL_POST, "_post"),
        ("Cancelar borrador", P.JOURNAL_CREATE, "_cancel"),
        ("Revertir", P.ENTRY_REVERSE, "_reverse"),
    ]

    def _load(self) -> None:
        date_from, date_to = self.period()
        self.set_table(self._presenter.journal_entries(
            status=self._status_id(), search=self._search.query(), date_from=date_from,
            date_to=date_to, limit=self.page_size, offset=self.offset))

    def _create(self) -> None:
        p = self._presenter
        dialog = JournalEntryDialog(self, accounts=p.postable_accounts(),
                                    journals=p.journal_type_options(),
                                    currencies=p.currency_options(),
                                    base_currency=p.base_currency())
        if dialog.exec_():
            self.run(p.create_journal_entry(**dialog.data()))

    def _detail(self) -> None:
        entry = self._presenter.journal_entry(self.selected_id())
        header = entry["header"]
        note = (f"{header.get('entry_number', '')} · {header.get('description', '')} · "
                f"creado por {header.get('created_by') or '—'} · "
                f"validado por {header.get('validated_by') or '—'} · "
                f"contabilizado por {header.get('posted_by') or '—'}")
        TableDialog(self, "Detalle del asiento", [
            ColumnSpec("Cuenta", "date"), ColumnSpec("Nombre"), ColumnSpec("Concepto"),
            ColumnSpec("Debe", "numeric"), ColumnSpec("Haber", "numeric"),
            ColumnSpec("Moneda", "status"), ColumnSpec("Tipo", "status"),
        ], entry["lines"], note=note).exec_()

    def _validate(self) -> None:
        self.run(self._presenter.validate_journal_entry(self.selected_id()))

    def _post(self) -> None:
        self.run(self._presenter.post_journal_entry(self.selected_id()))

    def _cancel(self) -> None:
        reason = ask_reason(self, "Cancelar borrador")
        if reason:
            self.run(self._presenter.cancel_journal_entry(self.selected_id(), reason))

    def _reverse(self) -> None:
        reason = ask_reason(self, "Revertir asiento", "Motivo del reverso")
        if reason:
            self.run(self._presenter.reverse_entry(self.selected_id(), reason))
