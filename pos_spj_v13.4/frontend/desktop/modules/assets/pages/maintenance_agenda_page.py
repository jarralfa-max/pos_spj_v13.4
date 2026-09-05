"""MaintenanceAgendaPage (ASSET-19, route ``assets.maintenance.calendar``) —
read-only agenda of scheduled work orders, sorted by date.

§96 describes a day/week/month calendar with vencido/hoy/próximo/bloqueado
indicators. This phase builds a plain date-sorted list instead — no
calendar-grid component exists anywhere in this codebase's Design System
(the master prompt's own §92/§96 components, like several others cited
across earlier ASSET-N docs, are aspirational names this repo hasn't built
yet), and a real "vencido"/"bloqueado" classification needs today's date
plus the same missing use-case layer noted in ``work_orders_board_page.py``.
This page shows what IS real — each open work order's own
``scheduled_at`` — without inventing a due/overdue judgment call the
backend hasn't made.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable, ViewState, create_state_widget
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class MaintenanceAgendaPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("maintenanceAgendaPage")
        self._presenter = presenter
        self._loaded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)
        root.addWidget(PageHeader(
            self, title="Agenda de mantenimiento",
            subtitle="Órdenes de trabajo abiertas, ordenadas por fecha programada.",
            icon=Icons.CALENDAR, compact=True))

        self._status = QLabel("", self)
        self._status.setObjectName("maintenanceAgendaStatus")
        self._status.setProperty("state", "ERROR")
        self._status.setWordWrap(True)
        self._status.hide()
        root.addWidget(self._status)

        self._table = StandardTable(
            [ColumnSpec("Folio"), ColumnSpec("Estado"), ColumnSpec("Prioridad"),
             ColumnSpec("Fecha programada", "date")], self)
        self._table.setAccessibleName("Agenda de órdenes de trabajo")
        self._empty = create_state_widget(
            ViewState.EMPTY, self, message="No hay órdenes de trabajo programadas")
        root.addWidget(self._table, stretch=1)
        root.addWidget(self._empty)
        self._table.hide()

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            work_orders = self._presenter.work_orders()
            scheduled = sorted(
                (wo for wo in work_orders if wo.scheduled_at), key=lambda wo: wo.scheduled_at)
            rows = [[wo.work_order_number, wo.status, wo.priority.value, wo.scheduled_at]
                    for wo in scheduled]
            row_ids = [wo.id for wo in scheduled]
            self._table.load_rows(rows, row_ids=row_ids)
            self._table.setVisible(bool(rows))
            self._empty.setVisible(not rows)
            self._loaded = True
            self._status.hide()
        except Exception as exc:  # a page must always show *something*
            self._status.setText(f"No fue posible cargar la agenda: {exc}")
            self._status.show()
