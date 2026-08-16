"""CASH-22 operational BI dashboard for Caja."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from backend.domain.cash_register.exceptions import CashRegisterError
from frontend.desktop.components.dashboard_grid import DashboardGrid
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.modules.cash_register.presentation import status_label, user_facing_error


class CashOverviewPage(QWidget):
    def __init__(self, *, presenter, parent=None):
        super().__init__(parent)
        self._presenter = presenter
        root = QVBoxLayout(self)
        root.addWidget(PageHeader(
            self,
            title="Resumen de caja",
            subtitle="Centro operativo: turno actual, alertas, cierres pendientes y siguiente accion.",
        ))
        self._grid = DashboardGrid(self)
        self._kpis = KPIBar(self)
        self._grid.add_kpi_bar(self._kpis)
        self._next_action = QLabel("", self)
        self._next_action.setObjectName("cashOverviewNextAction")
        self._next_action.setWordWrap(True)
        self._grid.add_full_width(self._next_action)
        self._freshness = QLabel("", self)
        self._freshness.setObjectName("cashOverviewFreshness")
        self._grid.add_full_width(self._freshness)
        self._active = self._table("Caja", "Estado", "Turno actual", "Apertura")
        self._closures = self._table("Caja", "Estado", "Accion requerida", "Apertura")
        self._differences = self._table("Diferencia", "Estado", "Detalle", "Fecha")
        self._handovers = self._table("Entrega", "Estado", "Detalle", "Preparada")
        self._terminals = self._table("Terminal", "Estado", "Detalle", "Actualizada")
        self._grid.add_row((self._active, 2), (self._closures, 1))
        self._grid.add_row((self._differences, 1), (self._handovers, 1))
        self._grid.add_row((self._terminals, 1))
        root.addWidget(self._grid)
        self._error = None
        self.refresh()

    def _table(self, first: str, status: str, detail: str, date: str) -> StandardTable:
        return StandardTable([
            ColumnSpec(first),
            ColumnSpec(status, "status"),
            ColumnSpec(detail),
            ColumnSpec(date, "date"),
        ], self)

    def refresh(self) -> None:
        try:
            dto = self._presenter.cash_overview_dashboard()
        except (CashRegisterError, RuntimeError, ValueError, LookupError) as exc:
            if self._error is None:
                self._error = create_state_widget(
                    ViewState.ERROR, self, message=user_facing_error(exc)
                )
                self.layout().addWidget(self._error)
            self._grid.setVisible(False)
            return
        if self._error is not None:
            self._error.setVisible(False)
        self._grid.setVisible(True)
        self._kpis.set_cards([
            KPIDTO(kpi.key, kpi.label, kpi.value, kpi.numeric_value)
            for kpi in dto.kpis
        ])
        self._next_action.setText(f"Siguiente accion: {dto.next_action}")
        self._freshness.setText(
            f"Actualizado con ultimo evento operativo: {dto.freshness or 'sin eventos registrados'}"
        )
        self._load(self._active, dto.active_shifts)
        self._load(self._closures, dto.pending_closures)
        self._load(self._differences, dto.pending_differences)
        self._load(self._handovers, dto.pending_handovers)
        self._load(self._terminals, dto.terminal_alerts)

    def _load(self, table: StandardTable, rows) -> None:
        table.load_rows(
            [[row.label, status_label(row.status), row.detail, row.occurred_at] for row in rows],
            row_ids=[row.id for row in rows],
        )
