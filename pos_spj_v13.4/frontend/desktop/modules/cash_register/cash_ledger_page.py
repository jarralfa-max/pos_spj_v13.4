"""CASH-8 ledger page wired to presenter commands."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QMessageBox, QVBoxLayout, QWidget

from backend.domain.cash_register.exceptions import CashAuthorizationRequiredError, CashRegisterError
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.modules.cash_register.cash_register_dialogs import (
    CashDenominationDialog,
    CashReasonDialog,
    HotAuthorizationDialog,
)
from frontend.desktop.modules.cash_register.presentation import (
    direction_label,
    display_code,
    movement_label,
    origin_label,
    user_facing_error,
)


class CashLedgerPage(QWidget):
    def __init__(self, query_service, *, shift_id: str | None, presenter=None, parent=None):
        super().__init__(parent)
        self._query, self._shift_id = query_service, shift_id
        self._presenter = presenter
        self._rows_by_id = {}
        root = QVBoxLayout(self)

        income = create_primary_button(self, "Registrar ingreso")
        withdrawal = create_secondary_button(self, "Registrar retiro")
        safe_drop = create_secondary_button(self, "Retiro a boveda")
        reverse = create_secondary_button(self, "Reversar")
        detail = create_secondary_button(self, "Ver detalle")
        origin = create_secondary_button(self, "Abrir documento origen")

        caps = self._presenter.capabilities() if self._presenter is not None else None
        has_shift = bool(self._shift_id)
        income.setEnabled(bool(has_shift and caps and caps.movement_income))
        withdrawal.setEnabled(bool(has_shift and caps and caps.movement_withdrawal))
        safe_drop.setEnabled(bool(has_shift and caps and caps.safe_drop_create))
        reverse.setEnabled(bool(has_shift and caps and caps.movement_reverse))
        detail.setEnabled(bool(has_shift and caps and caps.movement_view))
        origin.setEnabled(bool(has_shift and caps and caps.movement_view))

        income.clicked.connect(lambda: self._request_movement("MANUAL_INCOME", "Registrar ingreso"))
        withdrawal.clicked.connect(lambda: self._request_movement("MANUAL_WITHDRAWAL", "Registrar retiro"))
        safe_drop.clicked.connect(lambda: self._request_movement("SAFE_DROP", "Retiro a boveda"))
        reverse.clicked.connect(self._request_reversal)
        detail.clicked.connect(self._show_selected_detail)
        origin.clicked.connect(self._open_origin_document)

        root.addWidget(PageHeader(
            self,
            title="Movimientos de caja",
            subtitle="Entradas, salidas y saldo actual del turno.",
            actions=[origin, detail, reverse, safe_drop, withdrawal, income],
        ))

        if not has_shift:
            root.addWidget(create_state_widget(
                ViewState.EMPTY,
                self,
                message="No hay turno activo seleccionado. Abre o selecciona un turno para consultar movimientos.",
            ))
            self._kpis = KPIBar(self)
            self._table = StandardTable([], self)
            return

        self._kpis = KPIBar(self)
        root.addWidget(self._kpis)
        self._table = StandardTable([
            ColumnSpec("Fecha", "date"),
            ColumnSpec("Movimiento"),
            ColumnSpec("Concepto"),
            ColumnSpec("Entrada", "numeric"),
            ColumnSpec("Salida", "numeric"),
            ColumnSpec("Saldo", "numeric"),
            ColumnSpec("Reverso de"),
            ColumnSpec("Documento origen"),
        ], self)
        root.addWidget(self._table)
        self.refresh()

    @staticmethod
    def _money(value):
        return f"${value:,.2f}"

    def refresh(self):
        if not self._shift_id:
            return
        projection = self._query.projection(self._shift_id)
        self._rows_by_id = {row.id: row for row in projection.rows}
        self._kpis.set_cards([
            KPIDTO("balance", "Saldo", self._money(projection.balance), projection.balance),
            KPIDTO("inflows", "Entradas", self._money(projection.inflows), projection.inflows),
            KPIDTO("outflows", "Salidas", self._money(projection.outflows), projection.outflows),
            KPIDTO("count", "Movimientos", str(projection.movement_count), projection.movement_count),
        ])
        self._table.load_rows([
            [
                row.recorded_at,
                movement_label(row.movement_type),
                row.concept,
                self._money(row.amount) if row.direction == "INFLOW" else "—",
                self._money(row.amount) if row.direction == "OUTFLOW" else "—",
                self._money(row.balance),
                row.reversal_of_id or "—",
                row.reference_id or row.related_sale_id or "—",
            ]
            for row in projection.rows
        ], row_ids=[row.id for row in projection.rows])
        for row_index, row in enumerate(projection.rows):
            reversal = display_code("MOV", row.reversal_of_id) if row.reversal_of_id else "—"
            origin = origin_label(reference_id=row.reference_id, sale_id=row.related_sale_id)
            self._table.item(row_index, 6).setText(reversal)
            self._table.item(row_index, 6).setToolTip(reversal)
            self._table.item(row_index, 7).setText(origin)
            self._table.item(row_index, 7).setToolTip(origin)

    def _request_reversal(self):
        entry_id = self._table.selected_row_id()
        if not entry_id or self._presenter is None:
            return
        auth = HotAuthorizationDialog(self, title="Autorizar reverso")
        if auth.exec_() != auth.Accepted:
            return
        result = auth.result_value()
        try:
            response = self._presenter.reverse_cash_movement(
                entry_id=entry_id,
                authorized_by=result.authorizer_user,
                reason=result.reason,
            )
            self._show_result(getattr(response, "message", "Movimiento reversado"))
            self.refresh()
        except CashRegisterError as exc:
            self._show_error(user_facing_error(exc))

    def _request_movement(self, movement_type: str, title: str) -> None:
        if self._presenter is None:
            return
        reason_options = ()
        if movement_type == "SAFE_DROP":
            reason_options = tuple(self._presenter.movement_reason_options("SAFE_DROP"))
            if not reason_options:
                self._show_error("No hay motivos vigentes configurados para retiro a boveda.")
                return
        dialog = CashReasonDialog(self, title=title, reason_options=reason_options)
        if dialog.exec_() != dialog.Accepted:
            return
        result = dialog.result_value()
        concept = result.reason
        if result.notes:
            concept = f"{result.reason} - {result.notes}"
        try:
            response = self._presenter.register_cash_movement(
                movement_type=movement_type,
                amount=result.amount,
                concept=concept,
                reason_code=result.reason_code,
            )
        except CashAuthorizationRequiredError:
            auth = HotAuthorizationDialog(self, title="Autorizar movimiento")
            if auth.exec_() != auth.Accepted:
                return
            authorization = auth.result_value()
            try:
                response = self._presenter.register_cash_movement(
                    movement_type=movement_type,
                    amount=result.amount,
                    concept=concept,
                    reason_code=result.reason_code,
                    authorized_by=authorization.authorizer_user,
                )
            except CashRegisterError as exc:
                self._show_error(user_facing_error(exc))
                return
        except CashRegisterError as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(getattr(response, "message", "Movimiento registrado"))
        if movement_type == "SAFE_DROP":
            self._offer_prepare_handover(getattr(response, "entity_id", ""))
        self.refresh()

    def _selected_row(self):
        entry_id = self._table.selected_row_id()
        if not entry_id:
            self._show_error("Selecciona un movimiento.")
            return None
        row = self._rows_by_id.get(entry_id)
        if row is None:
            self._show_error("El movimiento seleccionado ya no esta disponible.")
        return row

    def _show_selected_detail(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        dialog = StandardDialog(self, title="Detalle de movimiento")
        title = QLabel(f"{movement_label(row.movement_type)}\n{self._money(row.amount)}", dialog)
        title.setProperty("role", "dialogTitle")
        body = QLabel(
            "\n".join((
                f"Fecha: {row.recorded_at}",
                f"Movimiento: {movement_label(row.movement_type)}",
                f"Direccion: {direction_label(row.direction)}",
                f"Concepto: {row.concept}",
                f"Documento origen: {origin_label(reference_id=row.reference_id, sale_id=row.related_sale_id)}",
                f"Reverso de: {display_code('MOV', row.reversal_of_id) if row.reversal_of_id else 'No aplica'}",
                f"Saldo del turno: {self._money(row.balance)}",
                "",
                "Detalles tecnicos disponibles en Auditoria.",
            )),
            dialog,
        )
        body.setWordWrap(True)
        dialog.content_layout().addWidget(title)
        dialog.content_layout().addWidget(body)
        dialog.add_button_box(ok_text="Cerrar")
        dialog.exec_()
        return
        QMessageBox.information(
            self,
            "Detalle de movimiento",
            "\n".join((
                "Detalles tecnicos disponibles en Auditoria.",
                f"Fecha: {row.recorded_at}",
                f"Tipo: {movement_label(row.movement_type)}",
                f"Direccion: {direction_label(row.direction)}",
                f"Importe: {self._money(row.amount)}",
                f"Saldo reconstruido: {self._money(row.balance)}",
                f"Concepto: {row.concept}",
                f"Origen: {row.reference_id or row.related_sale_id or '—'}",
                f"Reverso de: {row.reversal_of_id or '—'}",
            )),
        )

    def _open_origin_document(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        if not (row.reference_id or row.related_sale_id):
            self._show_error("El movimiento no tiene documento origen vinculado.")
            return
        QMessageBox.information(
            self,
            "Documento origen",
            f"Documento origen disponible para auditoria:\n{origin_label(reference_id=row.reference_id, sale_id=row.related_sale_id)}",
        )

    def _show_result(self, message: str) -> None:
        QMessageBox.information(self, "Caja", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Caja", user_facing_error(message))

    def _offer_prepare_handover(self, safe_drop_entry_id: str) -> None:
        if not safe_drop_entry_id or self._presenter is None:
            return
        answer = QMessageBox.question(
            self,
            "Entrega de valores",
            "El retiro a boveda fue registrado. ¿Preparar entrega de valores ahora?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        denominations = tuple(self._presenter.denomination_options())
        if not denominations:
            self._show_error("No hay denominaciones activas configuradas para preparar la entrega.")
            return
        dialog = CashDenominationDialog(
            self,
            title="Preparar entrega de valores",
            denominations=denominations,
        )
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            response = self._presenter.prepare_cash_handover(
                safe_drop_entry_id=safe_drop_entry_id,
                denominations=dialog.result_value().quantities,
            )
        except CashRegisterError as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(getattr(response, "message", "Entrega preparada"))
