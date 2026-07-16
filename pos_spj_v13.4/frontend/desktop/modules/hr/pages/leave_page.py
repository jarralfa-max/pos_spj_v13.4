"""Canonical HR leave page."""

from __future__ import annotations

<<<<<<< HEAD
from PyQt5.QtWidgets import QTableWidgetItem, QVBoxLayout, QWidget

from frontend.desktop.components import EmptyState, Icons, LoadingState, PageAction, PageHeader, PaginationBar, StandardTable, StatusBadge
=======
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import EmptyState, ErrorState, Icons, InlineFeedback, LoadingState, OfflineState, PageAction, PageHeader, PaginationBar, PartialState, PermissionState, StaleState, StandardTable, Toast
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
from frontend.desktop.modules.hr.hr_presenter import HRPresenterPort
from frontend.desktop.themes import DesktopSpacing


class HRLeavePage(QWidget):
    """Read-only leave request view backed by LeaveQueryService through the presenter."""

<<<<<<< HEAD
    HEADERS = ("Empleado", "Sucursal", "Tipo", "Periodo", "Días", "Estado", "Motivo")
=======
    HEADERS = ("ID", "Empleado", "Sucursal", "Tipo", "Periodo", "Días", "Estado", "Motivo")
    HIDDEN_HEADERS = ("ID",)
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23

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
<<<<<<< HEAD
        self._table = StandardTable(0, len(self.HEADERS), self)
        self._table.setHorizontalHeaderLabels(self.HEADERS)
=======
        self._install_state_feedback(layout)
        self._table = StandardTable(0, len(self.HEADERS), self)
        self._table.configure_headers(self.HEADERS, hidden_headers=self.HIDDEN_HEADERS)
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
        layout.addWidget(self._table, 1)
        self._pagination = PaginationBar(self, page_size=25)
        self._pagination.pageChanged.connect(lambda _limit, _offset: self.reload())
        layout.addWidget(self._pagination)
        self.reload()

<<<<<<< HEAD
    def reload(self) -> None:
        self._loading.setVisible(True)
=======
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

    def reload(self) -> None:
        self._loading.setVisible(True)
        self._hide_transient_states()
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
        try:
            rows = self._presenter.list_leave_requests(limit=self._pagination.limit, offset=self._pagination.offset) if self._presenter is not None else []
            self._empty.setVisible(len(rows) == 0)
            self._table.setVisible(len(rows) > 0)
            self._table.setRowCount(len(rows))
            for index, row in enumerate(rows):
<<<<<<< HEAD
                values = [row.employee_label, row.branch_label, row.leave_type, row.period, str(row.requested_days), row.status, row.reason]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    self._table.setItem(index, column, item)
                self._table.setCellWidget(index, 5, StatusBadge(row.status, self, status="warning" if row.status == "PENDING" else "neutral"))
            self._pagination.update_state(total_rows=len(rows))
=======
                values = [row.leave_request_id, row.employee_label, row.branch_label, row.leave_type, row.period, str(row.requested_days), row.status, row.reason]
                for column, value in enumerate(values):
                    self._table.set_text(index, column, value)
                self._table.set_status_badge(
                    index,
                    6,
                    row.status,
                    status="warning" if row.status == "PENDING" else "neutral",
                    tooltip="Estado de la solicitud de vacaciones o permiso",
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
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
        finally:
            self._loading.setVisible(False)
