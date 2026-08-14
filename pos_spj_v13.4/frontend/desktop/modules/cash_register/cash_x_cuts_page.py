"""CASH-13 non-final X cut workflow page."""

from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from backend.domain.cash_register.exceptions import CashRegisterError
from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.cash_register.cash_register_dialogs import CashTextReasonDialog
from frontend.desktop.modules.cash_register.presentation import display_code, user_facing_error


class CashXCutsPage(QWidget):
    def __init__(self, query_service, *, presenter, parent=None):
        super().__init__(parent)
        self._query = query_service
        self._presenter = presenter
        root = QVBoxLayout(self)
        generate = create_secondary_button(self, "Generar Corte X")
        print_cut = create_secondary_button(self, "Imprimir")
        reprint = create_secondary_button(self, "Reimprimir")
        caps = presenter.capabilities()
        generate.setEnabled(bool(caps.x_cut_generate))
        print_cut.setEnabled(bool(caps.x_cut_print))
        reprint.setEnabled(bool(caps.x_cut_reprint))
        generate.clicked.connect(self._generate)
        print_cut.clicked.connect(self._print)
        reprint.clicked.connect(self._reprint)
        root.addWidget(PageHeader(
            self,
            title="Corte X",
            subtitle="Documento parcial imprimible; no cierra, no reinicia y respeta importes sensibles.",
            actions=[reprint, print_cut, generate],
        ))
        self._kpis = KPIBar(self)
        root.addWidget(self._kpis)
        self._table = StandardTable([
            ColumnSpec("Documento"),
            ColumnSpec("Turno"),
            ColumnSpec("Esperado", "numeric"),
            ColumnSpec("Movimientos", "numeric"),
            ColumnSpec("Final"),
            ColumnSpec("Generado"),
        ], self)
        root.addWidget(self._table)
        self.refresh()

    @staticmethod
    def _money(value):
        return f"${value:,.2f}" if value is not None else "Restringido"

    def refresh(self) -> None:
        rows = self._query.list_for_branch(
            branch_id=self._presenter.active_branch_id(),
            requester_user_id=self._presenter.actor_user_id(),
        )
        visible_amounts = sum(1 for row in rows if row.sensitive_amounts_visible)
        self._kpis.set_cards([
            KPIDTO("cuts", "Cortes X", str(len(rows)), len(rows)),
            KPIDTO("visible", "Con importes", str(visible_amounts), visible_amounts),
            KPIDTO("redacted", "Restringidos", str(len(rows) - visible_amounts)),
        ])
        self._table.load_rows([
            [
                row.document_number,
                display_code("TUR", row.shift_id),
                self._money(row.expected_cash),
                (row.snapshot or {}).get("movement_count", "Restringido"),
                "No",
                row.generated_at,
            ]
            for row in rows
        ], row_ids=[row.id for row in rows])

    def _selected_cut_id(self) -> str | None:
        return self._table.selected_row_id()

    def _generate(self) -> None:
        try:
            result = self._presenter.generate_x_cut()
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(
            f"Corte X {getattr(result, 'document_number', '')} generado sin cerrar el turno."
        )
        self.refresh()

    def _print(self) -> None:
        self._print_selected(reprint=False)

    def _reprint(self) -> None:
        cut_id = self._selected_cut_id()
        if not cut_id:
            return
        dialog = CashTextReasonDialog(self, title="Motivo de reimpresion")
        if dialog.exec_() != dialog.Accepted:
            return
        self._print_selected(reprint=True, reason=dialog.result_value().reason)

    def _print_selected(self, *, reprint: bool, reason: str | None = None) -> None:
        cut_id = self._selected_cut_id()
        if not cut_id:
            return
        try:
            print_id = self._presenter.print_x_cut(
                cut_id=cut_id,
                reprint=reprint,
                reprint_reason=reason,
            )
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result("Corte X enviado a impresion." if print_id else "Corte X enviado a impresion.")

    def _show_result(self, message: str) -> None:
        QMessageBox.information(self, "Caja", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Caja", user_facing_error(message or "No fue posible completar Corte X."))
