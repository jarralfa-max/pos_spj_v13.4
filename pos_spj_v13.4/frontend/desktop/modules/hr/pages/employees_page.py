"""Employee page for the canonical HR desktop module."""

from __future__ import annotations

from PyQt5.QtWidgets import QInputDialog, QMenu, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import DebouncedSearchInput, EmptyState, ErrorState, FilterBar, Icons, InlineFeedback, LoadingState, OfflineState, PageAction, PageHeader, PaginationBar, PartialState, PermissionState, StaleState, StandardTable, Toast
from frontend.desktop.modules.hr.dialogs.employee_dialog import HREmployeeDialog
from frontend.desktop.modules.hr.hr_presenter import HRPresenterPort
from frontend.desktop.modules.hr.hr_view_models import HREmployeeRowViewModel
from frontend.desktop.themes import DesktopSpacing


class HREmployeesPage(QWidget):
    HEADERS = ("ID", "Código", "Empleado", "Sucursal", "Departamento", "Puesto", "Estado", "Fecha de ingreso", "Acciones")
    HIDDEN_HEADERS = ("ID",)

    def __init__(self, presenter: HRPresenterPort, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        root = QVBoxLayout(self)
        root.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        root.setSpacing(DesktopSpacing.MD)
        root.addWidget(
            PageHeader(
                title="Personal",
                subtitle="Alta, consulta y seguimiento de empleados desde el bounded context canónico.",
                icon=Icons.EMPLOYEE,
                actions=(
                    PageAction(
                        text="Nuevo empleado",
                        callback=self._request_create_employee,
                        variant="primary",
                        tooltip="Abrir formulario de alta de empleado.",
                    ),
                ),
                parent=self,
            )
        )

        self._filter_bar = FilterBar(self)
        toolbar = self._filter_bar
        self._search = DebouncedSearchInput(self)
        self._search.setPlaceholderText("Buscar personal por código, nombre o puesto")
        self._search.searchChanged.connect(self._search_changed)
        toolbar.add_filter(self._search, stretch=1, tooltip="Filtra personal con espera breve para no saturar el QueryService")
        toolbar.add_result_count()
        root.addWidget(toolbar)

        self._loading = LoadingState(parent=self)
        root.addWidget(self._loading)
        self._empty = EmptyState("Sin personal para mostrar", "Ajusta los filtros o crea un empleado nuevo.", self)
        root.addWidget(self._empty)
        self._install_state_feedback(root)
        self._table = StandardTable(0, len(self.HEADERS), self)
        self._table.configure_headers(self.HEADERS, hidden_headers=self.HIDDEN_HEADERS)
        self._table.setMinimumHeight(360)
        root.addWidget(self._table, 1)
        self._pagination = PaginationBar(self, page_size=25)
        self._pagination.pageChanged.connect(lambda _limit, _offset: self.refresh())
        root.addWidget(self._pagination)
        self.refresh()

    def _install_state_feedback(self, layout: QVBoxLayout) -> None:
        self._error = ErrorState(parent=self)
        self._offline = OfflineState(parent=self)
        self._stale = StaleState(parent=self)
        self._partial = PartialState(parent=self)
        self._permission = PermissionState(parent=self)
        self._feedback = InlineFeedback(parent=self, variant="info")
        self._toast = Toast(parent=self)
        for widget in (self._error, self._offline, self._stale, self._partial, self._permission, self._feedback, self._toast):
            widget.setVisible(False)
            layout.addWidget(widget)

    def _hide_transient_states(self) -> None:
        for widget in (self._error, self._offline, self._stale, self._partial, self._permission, self._feedback):
            widget.setVisible(False)

    def _show_error_state(self, message: str) -> None:
        self._table.setVisible(False)
        self._empty.setVisible(False)
        self._error.setVisible(True)
        self._feedback.setText(message)
        self._feedback.setProperty("variant", "danger")
        self._feedback.setVisible(True)

    def _search_changed(self, _text: str) -> None:
        self._pagination.reset()
        self.refresh()

    def refresh(self) -> None:
        self._loading.setVisible(True)
        self._hide_transient_states()
        try:
            rows = self._presenter.list_employees(search_text=self._search.text().strip(), limit=self._pagination.limit, offset=self._pagination.offset)
            self.render(rows)
            self._pagination.update_state(total_rows=len(rows))
        except PermissionError as exc:
            self._permission.setVisible(True)
            self._show_error_state(str(exc) or "No tienes permiso para ver esta información.")
        except ConnectionError as exc:
            self._offline.setVisible(True)
            self._show_error_state(str(exc) or "No se pudo conectar con la fuente de datos.")
        except Exception as exc:
            self._show_error_state(str(exc) or "No se pudo cargar la información.")
        finally:
            self._loading.setVisible(False)

    def render(self, rows: list[HREmployeeRowViewModel]) -> None:
        self._empty.setVisible(len(rows) == 0)
        self._filter_bar.set_result_count(len(rows))
        self._table.setVisible(len(rows) > 0)
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                row.employee_id,
                row.employee_code,
                row.full_name,
                row.branch_name,
                row.department_name,
                row.position_name,
                row.status,
                row.hire_date.isoformat() if row.hire_date else "",
            )
            for column, value in enumerate(values):
                self._table.set_text(row_index, column, value)
            self._table.set_status_badge(
                row_index,
                6,
                row.status,
                status="success" if row.status.upper() == "ACTIVE" else "neutral",
                tooltip="Estado laboral del empleado",
            )
            self._table.set_action_button(
                row_index,
                8,
                "Acciones",
                lambda employee_id=row.employee_id: self._open_row_actions(employee_id),
                tooltip="Abrir acciones disponibles para este empleado",
            )

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
