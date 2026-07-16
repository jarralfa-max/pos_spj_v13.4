"""Canonical HR attendance page."""

from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import EmptyState, ErrorState, Icons, InlineFeedback, LoadingState, OfflineState, PageAction, PageHeader, PaginationBar, PartialState, PermissionState, StaleState, StandardTable, Toast
from frontend.desktop.modules.hr.dialogs.attendance_dialog import HRAttendanceDialog
from frontend.desktop.modules.hr.hr_presenter import HRPresenterPort
from frontend.desktop.themes import DesktopSpacing


class HRAttendancePage(QWidget):
    """Renders attendance workdays and emits manual-registration actions."""

    HEADERS = ("ID", "Empleado", "Sucursal", "Entrada", "Salida", "Origen", "Horas", "Estado", "Incidencias", "Acciones")
    HIDDEN_HEADERS = ("ID",)

    def __init__(self, presenter: HRPresenterPort, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        layout.setSpacing(DesktopSpacing.MD)
        layout.addWidget(
            PageHeader(
                title="Asistencia",
                subtitle="Jornadas, marcaciones manuales e incidencias calculadas por RRHH canónico.",
                icon=Icons.ATTENDANCE,
                actions=(
                    PageAction(
                        text="Registrar asistencia",
                        callback=self._register_attendance,
                        variant="primary",
                        tooltip="Registrar una entrada o salida manual con motivo obligatorio.",
                    ),
                    PageAction(
                        text="Actualizar",
                        callback=self.refresh,
                        tooltip="Recargar jornadas desde AttendanceQueryService.",
                    ),
                ),
                parent=self,
            )
        )

        self._loading = LoadingState(parent=self)
        layout.addWidget(self._loading)
        self._empty = EmptyState("Sin jornadas de asistencia", "Las entradas, salidas e incidencias aparecerán aquí.", self)
        layout.addWidget(self._empty)
        self._install_state_feedback(layout)
        self._table = StandardTable(0, len(self.HEADERS), self)
        self._table.configure_headers(self.HEADERS, hidden_headers=self.HIDDEN_HEADERS)
        self._table.setMinimumHeight(360)
        layout.addWidget(self._table, 1)
        self._pagination = PaginationBar(self, page_size=25)
        self._pagination.pageChanged.connect(lambda _limit, _offset: self.refresh())
        layout.addWidget(self._pagination)
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

    def refresh(self) -> None:
        self._loading.setVisible(True)
        self._hide_transient_states()
        try:
            rows = self._presenter.list_attendance(limit=self._pagination.limit, offset=self._pagination.offset)
            self._empty.setVisible(len(rows) == 0)
            self._table.setVisible(len(rows) > 0)
            self._table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                values = (
                    row.workday_id,
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
                    self._table.set_text(index, column, value)
                self._table.set_status_badge(
                    index,
                    7,
                    row.status,
                    status="warning" if row.pending_incidents else "success",
                    tooltip="Estado de la jornada de asistencia",
                )
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
