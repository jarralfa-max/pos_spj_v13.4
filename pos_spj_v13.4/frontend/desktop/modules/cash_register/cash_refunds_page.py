"""Reembolsos ejecutados por Caja (CASH-17; re-auditado CASH-26 bloque 2).

Hasta el 2026-10-07 esta página no listaba nada: sólo abría un diálogo que
pedía el UUID del reembolso, el de la venta y el NOMBRE del autorizador (la
tabla exige su id), así que no podía completarse. Los reembolsos reales los
origina la devolución del POS (SALES-23), que ya decide el medio, pide
autorizador con clave y saca el efectivo del turno. Aquí se consultan.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from backend.application.cash_register.notification_text import money
from backend.domain.cash_register.exceptions import CashRegisterError
from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.modules.cash_register.cash_register_presenter import CashContextError
from frontend.desktop.modules.cash_register.presentation import (
    REFUND_METHOD_LABELS,
    user_facing_error,
)


class CashRefundsPage(QWidget):
    def __init__(self, *, presenter, parent=None):
        super().__init__(parent)
        self._presenter = presenter
        root = QVBoxLayout(self)
        refresh_button = create_secondary_button(self, "Actualizar")
        refresh_button.clicked.connect(self.refresh)
        root.addWidget(PageHeader(
            self,
            title="Reembolsos",
            subtitle="Devoluciones pagadas al cliente. Se hacen en Ventas → Devolver; "
                     "Caja registra la salida de efectivo del turno.",
            actions=[refresh_button],
        ))
        self._table = StandardTable([
            ColumnSpec("Fecha", "date"), ColumnSpec("Venta"), ColumnSpec("Medio", "status"),
            ColumnSpec("Monto", "numeric"), ColumnSpec("Entrego"), ColumnSpec("Autorizo"),
        ], self)
        root.addWidget(self._table)
        self.refresh()

    def refresh(self) -> None:
        try:
            rows = self._presenter.cash_refunds()
        except (CashRegisterError, CashContextError) as exc:
            self._table.load_rows([])
            apply_tooltip(self._table, user_facing_error(exc))
            return
        self._table.load_rows([
            [row.executed_at, row.sale_folio or "Sin folio",
             REFUND_METHOD_LABELS.get(row.method, row.method), money(row.amount),
             row.executed_by, row.authorized_by] for row in rows
        ], row_ids=[row.id for row in rows])
