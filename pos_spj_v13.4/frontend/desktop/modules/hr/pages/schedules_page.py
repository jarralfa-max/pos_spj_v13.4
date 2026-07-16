"""Canonical HR schedules page."""

from __future__ import annotations

from PyQt5.QtWidgets import QTableWidgetItem, QVBoxLayout, QWidget

from frontend.desktop.components import EmptyState, Icons, LoadingState, PageAction, PageHeader, PaginationBar, StandardTable, StatusBadge
from frontend.desktop.modules.hr.hr_presenter import HRPresenterPort
from frontend.desktop.themes import DesktopSpacing


class HRSchedulesPage(QWidget):
    """Read-only work-shift view backed by ShiftQueryService through the presenter."""

    HEADERS = ("Turno", "Sucursal", "Horario", "Descanso", "Tolerancia", "Estado")

    def __init__(self, presenter: HRPresenterPort | None = None, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        layout.setSpacing(DesktopSpacing.MD)
        layout.addWidget(
            PageHeader(
                title="Turnos laborales",
                subtitle="Turnos, tolerancias, descansos y asignaciones desde ShiftQueryService.",
                icon=Icons.SCHEDULE,
                actions=(
                    PageAction(
                        text="Actualizar turnos",
                        callback=self.reload,
                        variant="primary",
                        tooltip="Recargar turnos laborales desde ShiftQueryService.",
                    ),
                ),
                parent=self,
            )
        )
        self._loading = LoadingState(parent=self)
        layout.addWidget(self._loading)
        self._empty = EmptyState("Sin turnos configurados", "Los turnos, tolerancias y descansos aparecerán aquí.", self)
        layout.addWidget(self._empty)
        self._table = StandardTable(0, len(self.HEADERS), self)
        self._table.setHorizontalHeaderLabels(self.HEADERS)
        layout.addWidget(self._table, 1)
        self._pagination = PaginationBar(self, page_size=25)
        self._pagination.pageChanged.connect(lambda _limit, _offset: self.reload())
        layout.addWidget(self._pagination)
        self.reload()

    def reload(self) -> None:
        self._loading.setVisible(True)
        try:
            rows = self._presenter.list_shifts(limit=self._pagination.limit, offset=self._pagination.offset) if self._presenter is not None else []
            self._empty.setVisible(len(rows) == 0)
            self._table.setVisible(len(rows) > 0)
            self._table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                values = [row.name, row.branch_label, row.schedule, f"{row.break_minutes} min", f"{row.late_tolerance_minutes} min", "Activo" if row.active else "Inactivo"]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    self._table.setItem(index, column, item)
                self._table.setCellWidget(index, 5, StatusBadge(values[-1], self, status="success" if row.active else "neutral"))
            self._pagination.update_state(total_rows=len(rows))
        finally:
            self._loading.setVisible(False)
