"""Canonical HR attendance page."""

from __future__ import annotations

from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QHBoxLayout, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from frontend.desktop.components import EmptyState, LoadingState, PaginationBar, StatusBadge
from frontend.desktop.modules.hr.dialogs.attendance_dialog import HRAttendanceDialog
from frontend.desktop.modules.hr.hr_presenter import HRPresenterPort
from frontend.desktop.themes import DesktopSpacing


class HRAttendancePage(QWidget):
    """Renders attendance workdays and emits manual-registration actions."""

    HEADERS = ("Empleado", "Sucursal", "Entrada", "Salida", "Origen", "Horas", "Estado", "Incidencias", "Acciones")

    def __init__(self, presenter: HRPresenterPort, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        layout.setSpacing(DesktopSpacing.MD)

        actions = QHBoxLayout()
        self._register_button = QPushButton("Registrar asistencia", self)
        self._register_button.setToolTip("Registrar una entrada o salida manual con motivo obligatorio")
        self._register_button.clicked.connect(self._register_attendance)
        self._refresh_button = QPushButton("Actualizar", self)
        self._refresh_button.setToolTip("Recargar jornadas desde AttendanceQueryService")
        self._refresh_button.clicked.connect(self.refresh)
        actions.addWidget(self._register_button)
        actions.addWidget(self._refresh_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self._loading = LoadingState(parent=self)
        layout.addWidget(self._loading)
        self._empty = EmptyState("Sin jornadas de asistencia", "Las entradas, salidas e incidencias aparecerán aquí.", self)
        layout.addWidget(self._empty)
        self._table = QTableWidget(0, len(self.HEADERS), self)
        self._table.setHorizontalHeaderLabels(self.HEADERS)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setMinimumHeight(360)
        layout.addWidget(self._table, 1)
        self._pagination = PaginationBar(self, page_size=25)
        self._pagination.pageChanged.connect(lambda _limit, _offset: self.refresh())
        layout.addWidget(self._pagination)
        self.refresh()

    def refresh(self) -> None:
        self._loading.setVisible(True)
        try:
            rows = self._presenter.list_attendance(limit=self._pagination.limit, offset=self._pagination.offset)
            self._empty.setVisible(len(rows) == 0)
            self._table.setVisible(len(rows) > 0)
            self._table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                values = (
                    row.employee_label,
                    row.branch_label,
                    row.entry_at,
                    row.exit_at,
                    row.source_label,
                    f"{row.worked_hours:.2f}",
                    row.status,
                    str(row.pending_incidents),
                    "Solicitar corrección / Justificar / Auditoría",
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    self._table.setItem(index, column, item)
                self._table.setCellWidget(index, 6, StatusBadge(row.status, self, status="warning" if row.pending_incidents else "success"))
            self._pagination.update_state(total_rows=len(rows))
        finally:
            self._loading.setVisible(False)

    def _register_attendance(self) -> None:
        dialog = HRAttendanceDialog(self)
        if dialog.exec_() != dialog.Accepted:
            return
        form = dialog.form_value()
        if not form.reason.strip():
            QMessageBox.warning(self, "Motivo requerido", "El motivo es obligatorio para registros manuales.")
            return
        self._presenter.submit_manual_attendance(form)
        self.refresh()
