"""Employee page for the canonical HR desktop module."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QInputDialog, QMenu, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from frontend.desktop.components import DebouncedSearchInput, EmptyState, LoadingState, PaginationBar, StatusBadge
from frontend.desktop.modules.hr.dialogs.employee_dialog import HREmployeeDialog
from frontend.desktop.modules.hr.hr_presenter import HRPresenterPort
from frontend.desktop.modules.hr.hr_view_models import HREmployeeRowViewModel
from frontend.desktop.themes import DesktopSpacing


class HREmployeesPage(QWidget):
    HEADERS = ("Código", "Empleado", "Sucursal", "Departamento", "Puesto", "Estado", "Fecha de ingreso", "Acciones")

    def __init__(self, presenter: HRPresenterPort, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        root = QVBoxLayout(self)
        root.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        root.setSpacing(DesktopSpacing.MD)

        toolbar = QHBoxLayout()
        self._search = DebouncedSearchInput(self)
        self._search.setPlaceholderText("Buscar personal por código, nombre o puesto")
        self._search.setToolTip("Filtra personal con espera breve para no saturar el QueryService")
        self._search.searchChanged.connect(self._search_changed)
        create_button = QPushButton("Nuevo empleado", self)
        create_button.setToolTip("Abrir formulario de alta de empleado")
        create_button.clicked.connect(self._request_create_employee)
        toolbar.addWidget(self._search, 1)
        toolbar.addWidget(create_button)
        root.addLayout(toolbar)

        self._loading = LoadingState(parent=self)
        root.addWidget(self._loading)
        self._empty = EmptyState("Sin personal para mostrar", "Ajusta los filtros o crea un empleado nuevo.", self)
        root.addWidget(self._empty)
        self._table = QTableWidget(0, len(self.HEADERS), self)
        self._table.setHorizontalHeaderLabels(self.HEADERS)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setMinimumHeight(360)
        root.addWidget(self._table, 1)
        self._pagination = PaginationBar(self, page_size=25)
        self._pagination.pageChanged.connect(lambda _limit, _offset: self.refresh())
        root.addWidget(self._pagination)
        self.refresh()

    def _search_changed(self, _text: str) -> None:
        self._pagination.reset()
        self.refresh()

    def refresh(self) -> None:
        self._loading.setVisible(True)
        try:
            rows = self._presenter.list_employees(search_text=self._search.text().strip(), limit=self._pagination.limit, offset=self._pagination.offset)
            self.render(rows)
            self._pagination.update_state(total_rows=len(rows))
        finally:
            self._loading.setVisible(False)

    def render(self, rows: list[HREmployeeRowViewModel]) -> None:
        self._empty.setVisible(len(rows) == 0)
        self._table.setVisible(len(rows) > 0)
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                row.employee_code,
                row.full_name,
                row.branch_name,
                row.department_name,
                row.position_name,
                row.status,
                row.hire_date.isoformat() if row.hire_date else "",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, row.employee_id)
                item.setToolTip(value)
                self._table.setItem(row_index, column, item)
            badge = StatusBadge(row.status, self, status="success" if row.status.upper() == "ACTIVE" else "neutral")
            badge.setToolTip("Estado laboral del empleado")
            self._table.setCellWidget(row_index, 5, badge)
            action = QPushButton("Acciones", self)
            action.setToolTip("Abrir acciones disponibles para este empleado")
            action.setProperty("employee_id", row.employee_id)
            action.clicked.connect(lambda _checked=False, employee_id=row.employee_id: self._open_row_actions(employee_id))
            self._table.setCellWidget(row_index, 7, action)

    def _request_create_employee(self) -> None:
        dialog = HREmployeeDialog(self._presenter.load_employee_form_options(), self)
        if dialog.exec_() == dialog.Accepted:
            self._presenter.submit_create_employee(dialog.form())
            self.refresh()

    def _request_update_employee(self, employee_id: str) -> None:
        initial = self._presenter.load_employee_form(employee_id)
        if initial is None:
            QMessageBox.warning(self, "Empleado", "No se encontró el empleado seleccionado.")
            return
        dialog = HREmployeeDialog(self._presenter.load_employee_form_options(), self, initial=initial)
        if dialog.exec_() == dialog.Accepted:
            self._presenter.submit_update_employee(employee_id, dialog.form())
            self.refresh()

    def _open_row_actions(self, employee_id: str) -> None:
        menu = QMenu(self)
        edit_action = menu.addAction("Editar")
        deactivate_action = menu.addAction("Dar de baja")
        selected = menu.exec_(self.cursor().pos())
        if selected == edit_action:
            self._request_update_employee(employee_id)
        elif selected == deactivate_action:
            self._request_deactivate_employee(employee_id)

    def _request_deactivate_employee(self, employee_id: str) -> None:
        reason, accepted = QInputDialog.getText(self, "Baja de empleado", "Motivo de baja")
        if not accepted:
            return
        if not reason.strip():
            QMessageBox.warning(self, "Baja de empleado", "El motivo de baja es obligatorio.")
            return
        confirm = QMessageBox.question(self, "Baja de empleado", "¿Confirmas la baja del empleado seleccionado?")
        if confirm == QMessageBox.Yes:
            self._presenter.submit_deactivate_employee(employee_id, reason.strip())
            self.refresh()
