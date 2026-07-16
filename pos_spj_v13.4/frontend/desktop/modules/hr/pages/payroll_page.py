"""Canonical HR payroll page."""

from __future__ import annotations

from PyQt5.QtWidgets import QTableWidgetItem, QVBoxLayout, QWidget

from frontend.desktop.components import EmptyState, Icons, LoadingState, PageAction, PageHeader, PaginationBar, StandardTable, StatusBadge
from frontend.desktop.modules.hr.hr_presenter import HRPresenterPort
from frontend.desktop.themes import DesktopSpacing


class HRPayrollPage(QWidget):
    """Read-only payroll run page backed by PayrollQueryService through the presenter."""

    HEADERS = ("Sucursal", "Periodo", "Estado", "Bruto", "Deducciones", "Neto")

    def __init__(self, presenter: HRPresenterPort | None = None, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        layout.setSpacing(DesktopSpacing.MD)
        layout.addWidget(
            PageHeader(
                title="Nómina",
                subtitle="Corridas, autorización y pagos consultados desde PayrollQueryService.",
                icon=Icons.PAYROLL,
                actions=(
                    PageAction(
                        text="Actualizar corridas",
                        callback=self.reload,
                        variant="primary",
                        tooltip="Recargar corridas desde PayrollQueryService.",
                    ),
                ),
                parent=self,
            )
        )
        self._loading = LoadingState(parent=self)
        layout.addWidget(self._loading)
        self._empty = EmptyState("Sin corridas de nómina", "Las corridas calculadas, autorizadas o pagadas aparecerán aquí.", self)
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
            rows = self._presenter.list_payroll_runs(limit=self._pagination.limit, offset=self._pagination.offset) if self._presenter is not None else []
            self._empty.setVisible(len(rows) == 0)
            self._table.setVisible(len(rows) > 0)
            self._table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                values = [row.branch_label, row.period, row.status, str(row.gross_amount), str(row.deductions_amount), str(row.net_amount)]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    self._table.setItem(index, column, item)
                self._table.setCellWidget(index, 2, StatusBadge(row.status, self, status="success" if row.status == "PAID" else "neutral"))
            self._pagination.update_state(total_rows=len(rows))
        finally:
            self._loading.setVisible(False)
