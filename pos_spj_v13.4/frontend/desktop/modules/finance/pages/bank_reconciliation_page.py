"""Conciliación bancaria — espacio de trabajo completo (auditoría F23).

Antes la página sólo listaba conciliaciones: no había forma de importar,
iniciar, emparejar, completar ni revertir desde el módulo, aunque los casos de
uso existían. Ahora:

* Importar estado → captura el estado y abre su conciliación.
* Conciliar partidas → estado y mayor lado a lado; sólo aparecen líneas
  elegibles (de la cuenta espejo, contabilizadas, sin match activo).
* Completar → exige todo conciliado o el motivo de la diferencia aceptada
  (permiso aparte).
* Revertir → con motivo; las partidas vuelven a quedar disponibles.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from frontend.desktop.components.buttons import (
    create_danger_button,
    create_primary_button,
    create_secondary_button,
    create_success_button,
)
from frontend.desktop.components.dialogs import FormDialog, StandardDialog
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class ReconciliationWorkspaceDialog(StandardDialog):
    """Estado de cuenta y libro mayor lado a lado para emparejar."""

    def __init__(self, parent, presenter, reconciliation_id: str) -> None:
        super().__init__(parent, title="Conciliar partidas")
        self._presenter = presenter
        self._reconciliation_id = reconciliation_id
        root = self.content_layout()
        sides = QHBoxLayout()
        left, right = QVBoxLayout(), QVBoxLayout()
        left.addWidget(QLabel("Estado de cuenta (pendientes)"))
        self.statement_table = StandardTable([
            ColumnSpec("Fecha", "date"), ColumnSpec("Descripción"),
            ColumnSpec("Importe", "numeric"), ColumnSpec("Referencia", "date")], self)
        left.addWidget(self.statement_table)
        right.addWidget(QLabel("Libro mayor (cuenta espejo, sin conciliar)"))
        self.ledger_table = StandardTable([
            ColumnSpec("Fecha", "date"), ColumnSpec("Asiento", "date"),
            ColumnSpec("Descripción"), ColumnSpec("Debe", "numeric"),
            ColumnSpec("Haber", "numeric")], self)
        right.addWidget(self.ledger_table)
        sides.addLayout(left, 1)
        sides.addLayout(right, 1)
        root.addLayout(sides)
        self.message = QLabel("", self)
        self.message.setWordWrap(True)
        root.addWidget(self.message)
        match_btn = create_primary_button(self, "Emparejar seleccionadas")
        match_btn.clicked.connect(self._match)
        self.add_footer_widget(match_btn)
        self.add_button_box(ok_text="Cerrar", on_accept=self.accept)
        self.refresh()

    def refresh(self) -> None:
        data = self._presenter.reconciliation_candidates(self._reconciliation_id)
        self.statement_table.load_rows(data["statement"].rows,
                                       row_ids=data["statement"].row_ids)
        self.ledger_table.load_rows(data["ledger"].rows, row_ids=data["ledger"].row_ids)

    def _match(self) -> None:
        statement_line = self.statement_table.selected_row_id()
        ledger_line = self.ledger_table.selected_row_id()
        if not statement_line or not ledger_line:
            self.message.setText("Seleccione una partida del estado y una línea del mayor.")
            return
        ok, text = self._presenter.match_reconciliation(
            reconciliation_id=self._reconciliation_id,
            bank_statement_line_id=statement_line, journal_line_id=ledger_line)
        self.message.setText(text)
        if ok:
            self.refresh()


class BankReconciliationPage(FinancePage):
    title = "Conciliación bancaria"
    subtitle = "Estados importados y matching contra el libro mayor"
    columns = [
        ColumnSpec("Cuenta de tesorería"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Completó", "date"),
        ColumnSpec("Fecha", "date"),
    ]

    def _build_actions(self) -> None:
        import_btn = create_primary_button(self, "Importar estado")
        import_btn.clicked.connect(self._import_statement)
        self.header.add_action(import_btn)

    def _build_row_actions(self, row: QHBoxLayout) -> None:
        match_btn = create_secondary_button(self, "Conciliar partidas")
        match_btn.clicked.connect(self._open_workspace)
        complete_btn = create_success_button(self, "Completar")
        complete_btn.clicked.connect(self._complete)
        revert_btn = create_danger_button(self, "Revertir")
        revert_btn.clicked.connect(self._revert)
        for button in (match_btn, complete_btn, revert_btn):
            row.addWidget(button)

    def _import_statement(self) -> None:
        from frontend.desktop.modules.finance.dialogs.statement_import_dialog import (
            StatementImportDialog,
        )
        dialog = StatementImportDialog(self, self._presenter.treasury_accounts())
        if not dialog.exec_():
            return
        data = dialog.data()
        ok, message = self._presenter.import_bank_statement(**data)
        if ok:
            statements = self._presenter.bank_statements(data["treasury_account_id"])
            if statements:
                ok, message = self._presenter.start_reconciliation(statements[0][0])
        self.notify(ok, message)
        self.reload()

    def _selected_or_warn(self) -> str | None:
        reconciliation_id = self.table.selected_row_id()
        if not reconciliation_id:
            self.notify(False, "Seleccione una conciliación.")
        return reconciliation_id

    def _open_workspace(self) -> None:
        reconciliation_id = self._selected_or_warn()
        if reconciliation_id:
            ReconciliationWorkspaceDialog(self, self._presenter, reconciliation_id).exec_()
            self.reload()

    def _complete(self) -> None:
        reconciliation_id = self._selected_or_warn()
        if not reconciliation_id:
            return
        ok, message = self._presenter.complete_reconciliation(reconciliation_id)
        if not ok and "sin conciliar" in message:
            reason, accepted = FormDialog.get_text(
                self, "Diferencia aceptada",
                f"{message}\nMotivo de la diferencia (requiere permiso para aceptarla):")
            if accepted and reason.strip():
                ok, message = self._presenter.complete_reconciliation(
                    reconciliation_id, difference_reason=reason.strip())
        self.notify(ok, message)
        self.reload()

    def _revert(self) -> None:
        reconciliation_id = self._selected_or_warn()
        if not reconciliation_id:
            return
        reason, accepted = FormDialog.get_text(self, "Revertir conciliación", "Motivo:")
        if accepted and reason.strip():
            self.notify(*self._presenter.revert_reconciliation(reconciliation_id,
                                                               reason.strip()))
            self.reload()

    def _load(self) -> None:
        self.set_table(self._presenter.reconciliations())
