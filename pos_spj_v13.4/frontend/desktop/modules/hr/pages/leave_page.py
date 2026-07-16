"""Canonical HR leave page."""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import EmptyState, ErrorState, Icons, InlineFeedback, LoadingState, OfflineState, PageAction, PageHeader, PaginationBar, PartialState, PermissionState, StaleState, StandardTable, Toast
from frontend.desktop.modules.hr.hr_presenter import HRPresenterPort
from frontend.desktop.themes import DesktopSpacing


class HRLeavePage(QWidget):
    """Read-only leave request view backed by LeaveQueryService through the presenter."""

    HEADERS = ("Empleado", "Sucursal", "Tipo", "Periodo", "Días", "Estado", "Motivo")

    def __init__(self, presenter: HRPresenterPort | None = None, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        layout.setSpacing(DesktopSpacing.MD)
        layout.addWidget(
            PageHeader(
                title="Vacaciones y permisos",
                subtitle="Solicitudes, aprobaciones y estado de permisos desde LeaveQueryService.",
                icon=Icons.LEAVE,
                actions=(
                    PageAction(
                        text="Actualizar solicitudes",
                        callback=self.reload,
                        variant="primary",
                        tooltip="Recargar vacaciones y permisos desde LeaveQueryService.",
                    ),
                ),
                parent=self,
            )
        )
        self._loading = LoadingState(parent=self)
        layout.addWidget(self._loading)
        self._empty = EmptyState("Sin solicitudes de vacaciones o permisos", "Las solicitudes pendientes, aprobadas o rechazadas aparecerán aquí.", self)
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
            rows = self._presenter.list_leave_requests(limit=self._pagination.limit, offset=self._pagination.offset) if self._presenter is not None else []
            self._empty.setVisible(len(rows) == 0)
            self._table.setVisible(len(rows) > 0)
            self._table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                values = [row.employee_label, row.branch_label, row.leave_type, row.period, str(row.requested_days), row.status, row.reason]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    self._table.setItem(index, column, item)
                self._table.setCellWidget(index, 5, StatusBadge(row.status, self, status="warning" if row.status == "PENDING" else "neutral"))
            self._pagination.update_state(total_rows=len(rows))
        finally:
            self._loading.setVisible(False)
