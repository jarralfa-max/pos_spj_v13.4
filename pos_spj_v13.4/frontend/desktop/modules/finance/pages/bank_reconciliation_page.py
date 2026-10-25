"""Conciliación bancaria (§15) — espacio de trabajo completo.

* Importar estado (CSV/XLSX o captura) → se revisa y se importa.
* Iniciar conciliación sobre un estado importado.
* Conciliar partidas: estado y mayor lado a lado; sugerencias por importe,
  fecha y referencia; emparejar, ignorar con motivo o registrar el ajuste
  (comisión, interés) con su asiento.
* Completar: todo conciliado o diferencia aceptada con motivo (permiso aparte).
* Revertir: con motivo; las partidas vuelven a quedar disponibles.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask, ask_reason
from frontend.desktop.modules.finance.dialogs.statement_import_dialog import (
    StatementImportDialog,
)
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class ReconciliationWorkspaceDialog(StandardDialog):
    """Estado de cuenta y libro mayor lado a lado."""

    def __init__(self, parent, presenter, reconciliation_id: str) -> None:
        super().__init__(parent, title="Conciliar partidas", width=1100)
        self._presenter = presenter
        self._reconciliation_id = reconciliation_id
        self._suggested: dict[str, str] = {}
        root = self.content_layout()
        sides = QHBoxLayout()
        left, right = QVBoxLayout(), QVBoxLayout()
        left.addWidget(QLabel("Estado de cuenta (pendientes)"))
        self.statement_table = StandardTable([
            ColumnSpec("Fecha", "date"), ColumnSpec("Descripción"),
            ColumnSpec("Importe", "numeric"), ColumnSpec("Referencia", "date"),
            ColumnSpec("Estado", "status")], self)
        self.statement_table.itemSelectionChanged.connect(self._follow_suggestion)
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
        actions = [
            (create_secondary_button(self, "Sugerir coincidencias"), self._suggest,
             P.RECONCILIATION_OPERATE),
            (create_primary_button(self, "Emparejar seleccionadas"), self._match,
             P.RECONCILIATION_OPERATE),
            (create_secondary_button(self, "Ignorar partida"), self._ignore,
             P.RECONCILIATION_OPERATE),
            (create_secondary_button(self, "Registrar ajuste"), self._adjust,
             P.RECONCILIATION_ADJUST),
        ]
        for button, handler, permission in actions:
            button.clicked.connect(handler)
            if not presenter.can(permission):
                button.setEnabled(False)
                button.setToolTip(f"Requiere el permiso {permission}")
            self.add_footer_widget(button)
        self.add_button_box(ok_text="Cerrar", on_accept=self.accept)
        self.refresh()

    def refresh(self) -> None:
        data = self._presenter.reconciliation_candidates(self._reconciliation_id)
        self._suggested = data.get("suggested", {})
        self.statement_table.load_rows(data["statement"].rows,
                                       row_ids=data["statement"].row_ids)
        self.ledger_table.load_rows(data["ledger"].rows, row_ids=data["ledger"].row_ids)

    def _say(self, result: tuple[bool, str]) -> None:
        ok, text = result
        self.message.setText(text)
        if ok:
            self.refresh()

    def _follow_suggestion(self) -> None:
        suggested = self._suggested.get(self.statement_table.selected_row_id() or "")
        if not suggested:
            return
        for row in range(self.ledger_table.rowCount()):
            item = self.ledger_table.item(row, 0)
            if item is not None and item.data(Qt.UserRole) == suggested:
                self.ledger_table.selectRow(row)
                return

    def _suggest(self) -> None:
        self._say(self._presenter.suggest_matches(self._reconciliation_id))

    def _match(self) -> None:
        statement_line = self.statement_table.selected_row_id()
        ledger_line = self.ledger_table.selected_row_id()
        if not statement_line or not ledger_line:
            self.message.setText("Elija una partida del estado y una línea del mayor.")
            return
        self._say(self._presenter.match_reconciliation(
            reconciliation_id=self._reconciliation_id,
            bank_statement_line_id=statement_line, journal_line_id=ledger_line))

    def _ignore(self) -> None:
        statement_line = self.statement_table.selected_row_id()
        if not statement_line:
            self.message.setText("Elija la partida del estado a ignorar.")
            return
        reason = ask_reason(self, "Ignorar partida", "Por qué no se concilia")
        if reason:
            self._say(self._presenter.ignore_statement_line(
                reconciliation_id=self._reconciliation_id,
                bank_statement_line_id=statement_line, reason=reason))

    def _adjust(self) -> None:
        statement_line = self.statement_table.selected_row_id()
        if not statement_line:
            self.message.setText("Elija la partida del estado que origina el ajuste.")
            return
        p = self._presenter
        values = ask(self, "Ajuste de conciliación", [
            FieldSpec("kind", "Tipo", "combo", options=p.movement_kind_options()),
            FieldSpec("counterpart_account_id", "Contrapartida (vacío: la del perfil)", "combo",
                      options=p.postable_accounts()),
            FieldSpec("reason", "Motivo", "multiline", required=True),
        ])
        if values:
            self._say(p.reconciliation_adjustment(
                reconciliation_id=self._reconciliation_id,
                bank_statement_line_id=statement_line, **values))


class BankReconciliationPage(FinancePage):
    title = "Conciliación bancaria"
    subtitle = "Estados importados y su conciliación contra el libro mayor"
    columns = [
        ColumnSpec("Cuenta de tesorería"),
        ColumnSpec("Estado de cuenta", "date"),
        ColumnSpec("Estatus", "status"),
        ColumnSpec("Pendientes", "numeric"),
        ColumnSpec("Completó", "date"),
        ColumnSpec("Fecha", "date"),
        ColumnSpec("Diferencia / reverso"),
    ]
    header_actions = [
        ("Importar estado", P.STATEMENT_IMPORT, "_import_statement", True),
        ("Iniciar conciliación", P.RECONCILIATION_OPERATE, "_start", False),
    ]
    row_actions = [
        ("Conciliar partidas", P.RECONCILIATION_OPERATE, "_open_workspace"),
        ("Completar", P.RECONCILIATION_OPERATE, "_complete"),
        ("Revertir", P.RECONCILIATION_REVERT, "_revert"),
    ]

    def _load(self) -> None:
        self.set_table(self._presenter.reconciliations())

    def _import_statement(self) -> None:
        p = self._presenter
        dialog = StatementImportDialog(self, p.bank_accounts(), read_file=p.read_statement_file,
                                       parse_manual=p.parse_manual_statement)
        if dialog.exec_():
            self.run(p.import_bank_statement(**dialog.data()))

    def _start(self) -> None:
        statements = self._presenter.pending_statements()
        if not statements:
            self.notify(False, "No hay estados de cuenta pendientes de conciliar.")
            return
        values = ask(self, "Iniciar conciliación", [
            FieldSpec("statement_id", "Estado de cuenta", "combo", required=True,
                      options=statements)])
        if values:
            self.run(self._presenter.start_reconciliation(values["statement_id"]))

    def _open_workspace(self) -> None:
        ReconciliationWorkspaceDialog(self, self._presenter, self.selected_id()).exec_()
        self.reload()

    def _complete(self) -> None:
        reconciliation_id = self.selected_id()
        ok, message = self._presenter.complete_reconciliation(reconciliation_id)
        if not ok and "sin conciliar" in message:
            reason = ask_reason(self, "Aceptar diferencia",
                                f"{message}. Motivo de la diferencia aceptada")
            if reason:
                ok, message = self._presenter.complete_reconciliation(
                    reconciliation_id, difference_reason=reason)
        self.notify(ok, message)

    def _revert(self) -> None:
        reason = ask_reason(self, "Revertir conciliación")
        if reason:
            self.run(self._presenter.revert_reconciliation(self.selected_id(), reason))
