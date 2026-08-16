"""CASH-14 final Z cut workflow page."""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from backend.domain.cash_register.exceptions import CashRegisterError
from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.cash_register.cash_register_dialogs import ReprintCashDocumentDialog
from frontend.desktop.modules.cash_register.presentation import display_code, user_facing_error


class CashZCutsPage(QWidget):
    def __init__(self, query_service, *, presenter, parent=None):
        super().__init__(parent)
        self._query = query_service
        self._presenter = presenter
        root = QVBoxLayout(self)
        generate = create_secondary_button(self, "Generar Corte Z")
        print_cut = create_secondary_button(self, "Imprimir")
        reprint = create_secondary_button(self, "Reimprimir")
        notify = create_secondary_button(self, "Notificar")
        caps = presenter.capabilities()
        generate.setEnabled(bool(caps.z_cut_generate))
        print_cut.setEnabled(bool(caps.z_cut_print))
        reprint.setEnabled(bool(caps.z_cut_reprint))
        notify.setEnabled(bool(caps.notification_manage))
        generate.clicked.connect(self._generate)
        print_cut.clicked.connect(self._print)
        reprint.clicked.connect(self._reprint)
        notify.clicked.connect(self._notify)
        root.addWidget(PageHeader(
            self,
            title="Corte Z",
            subtitle="Consolida conteo confirmado, calcula esperado, crea diferencia y cierra el turno.",
            actions=[notify, reprint, print_cut, generate],
        ))
        self._kpis = KPIBar(self)
        root.addWidget(self._kpis)
        self._table = StandardTable([
            ColumnSpec("Documento"),
            ColumnSpec("Turno"),
            ColumnSpec("Esperado", "numeric"),
            ColumnSpec("Contado", "numeric"),
            ColumnSpec("Diferencia", "numeric"),
            ColumnSpec("Final"),
            ColumnSpec("Generado"),
        ], self)
        self._rows_by_id = {}
        root.addWidget(self._table)
        self.refresh()

    @staticmethod
    def _money(value):
        return f"${value:,.2f}"

    def refresh(self) -> None:
        rows = self._query.list_for_branch(
            branch_id=self._presenter.active_branch_id(),
            requester_user_id=self._presenter.actor_user_id(),
        )
        self._rows_by_id = {row.id: row for row in rows}
        total_difference = sum((row.difference for row in rows), Decimal("0"))
        self._kpis.set_cards([
            KPIDTO("cuts", "Cortes Z", str(len(rows)), len(rows)),
            KPIDTO("final", "Finales", str(sum(1 for row in rows if row.is_final))),
            KPIDTO("diff", "Diferencia neta", self._money(total_difference), total_difference),
        ])
        self._table.load_rows([
            [
                row.document_number,
                display_code("TUR", row.shift_id),
                self._money(row.expected_cash),
                self._money(row.counted_cash),
                self._money(row.difference),
                "Si" if row.is_final else "No",
                row.generated_at,
            ]
            for row in rows
        ], row_ids=[row.id for row in rows])

    def _selected_cut_id(self) -> str | None:
        return self._table.selected_row_id()

    def _generate(self) -> None:
        answer = QMessageBox.question(
            self,
            "Cerrar turno",
            "Se generara el Corte Z final y el turno quedara cerrado. Verifica que el conteo este confirmado.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            result = self._presenter.generate_z_cut()
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(
            f"Corte Z {getattr(result, 'document_number', '')} generado y turno cerrado."
        )
        self.refresh()

    def _print(self) -> None:
        self._print_selected(reprint=False)

    def _reprint(self) -> None:
        cut_id = self._selected_cut_id()
        if not cut_id:
            return
        dialog = ReprintCashDocumentDialog(
            self,
            document_type="Corte Z",
            document=self._rows_by_id.get(cut_id),
        )
        if dialog.exec_() != dialog.Accepted:
            return
        self._print_selected(reprint=True, reason=dialog.result_value().reason)

    def _print_selected(self, *, reprint: bool, reason: str | None = None) -> None:
        cut_id = self._selected_cut_id()
        if not cut_id:
            return
        try:
            print_id = self._presenter.print_z_cut(
                cut_id=cut_id,
                reprint=reprint,
                reprint_reason=reason,
            )
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result("Corte Z enviado a impresion." if print_id else "Corte Z enviado a impresion.")

    def _notify(self) -> None:
        cut_id = self._selected_cut_id()
        if not cut_id:
            return
        try:
            result = self._presenter.notify_z_cut(cut_id=cut_id)
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(
            f"Notificacion preparada para {getattr(result, 'document_number', 'el Corte Z seleccionado')}"
        )

    def _show_result(self, message: str) -> None:
        QMessageBox.information(self, "Caja", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Caja", user_facing_error(message or "No fue posible completar Corte Z."))
