"""Presupuestos (§16): flujo borrador → enviado → aprobado → activo → cerrado,
versiones y ejecución por partida (comprometido, devengado, pagado,
disponible y nivel de control)."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.dialogs.budget_dialog import BudgetDialog
from frontend.desktop.modules.finance.dialogs.fields_dialog import ask_reason
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class BudgetsPage(FinancePage):
    title = "Presupuestos"
    subtitle = "Lo comprometido, devengado y pagado se compara contra lo aprobado"
    columns = [
        ColumnSpec("Nombre"),
        ColumnSpec("Año", "date"),
        ColumnSpec("Versión", "status"),
        ColumnSpec("Control", "status"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Aprobó", "date"),
        ColumnSpec("Motivo de rechazo"),
    ]
    header_actions = [("Nuevo presupuesto", P.BUDGET_CREATE, "_create", True)]
    row_actions = [
        ("Enviar", P.BUDGET_CREATE, "_submit"),
        ("Aprobar", P.BUDGET_APPROVE, "_approve"),
        ("Rechazar", P.BUDGET_APPROVE, "_reject"),
        ("Activar", P.BUDGET_APPROVE, "_activate"),
        ("Nueva versión", P.BUDGET_CREATE, "_version"),
        ("Cerrar", P.BUDGET_APPROVE, "_close"),
        ("Cancelar", P.BUDGET_APPROVE, "_cancel"),
    ]

    def _build_extra(self) -> None:
        self._execution_title = QLabel("Ejecución del año en curso", self)
        self._execution_title.setProperty("role", "muted")
        self._layout.addWidget(self._execution_title)
        self._execution = StandardTable([
            ColumnSpec("Periodo", "date"), ColumnSpec("Cuenta"),
            ColumnSpec("Aprobado", "numeric"), ColumnSpec("Comprometido", "numeric"),
            ColumnSpec("Devengado", "numeric"), ColumnSpec("Pagado", "numeric"),
            ColumnSpec("Disponible", "numeric"), ColumnSpec("Consumido", "numeric"),
            ColumnSpec("Control", "status"),
        ], self)
        self._execution.setMaximumHeight(220)
        self._layout.addWidget(self._execution)
        self._table.itemSelectionChanged.connect(self._show_execution)

    def _load(self) -> None:
        self.set_table(self._presenter.budgets())
        self._show_execution()

    def _show_execution(self) -> None:
        year = self._presenter.today().year
        budget_id = self.selected_id()
        if budget_id:
            row = self._table.currentRow()
            year = int(self._table.item(row, 1).text())
            self._execution_title.setText("Ejecución del presupuesto elegido")
        else:
            self._execution_title.setText(f"Ejecución de presupuestos vigentes {year}")
        model = self._presenter.budget_execution(year, budget_id)
        self._execution.load_rows(model.rows, row_ids=model.row_ids)

    def _create(self) -> None:
        dialog = BudgetDialog(self, self._presenter.expense_accounts(),
                              self._presenter.today().year)
        if dialog.exec_():
            self.run(self._presenter.create_budget(**dialog.data()))

    def _action(self, action: str, reason: str = "") -> None:
        self.run(self._presenter.budget_action(self.selected_id(), action, reason))

    def _submit(self) -> None:
        self._action("submit")

    def _approve(self) -> None:
        self._action("approve")

    def _activate(self) -> None:
        self._action("activate")

    def _close(self) -> None:
        self._action("close")

    def _reject(self) -> None:
        reason = ask_reason(self, "Rechazar presupuesto")
        if reason:
            self._action("reject", reason)

    def _cancel(self) -> None:
        reason = ask_reason(self, "Cancelar presupuesto")
        if reason:
            self._action("cancel", reason)

    def _version(self) -> None:
        self.run(self._presenter.create_budget_version(self.selected_id()))
