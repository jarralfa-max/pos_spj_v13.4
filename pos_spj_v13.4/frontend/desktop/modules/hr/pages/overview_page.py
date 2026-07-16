"""HR dashboard overview page."""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import EmptyState, ErrorState, Icons, InlineFeedback, KPIBar, KPIDTO, LoadingState, OfflineState, PageAction, PageHeader, PartialState, PermissionState, StaleState, Toast
from frontend.desktop.modules.hr.hr_presenter import HRPresenterPort
from frontend.desktop.modules.hr.hr_view_models import HRDashboardKpiViewModel
from frontend.desktop.themes import DesktopSpacing


class HROverviewPage(QWidget):
    """Dashboard page: KPI values come from HRDashboardQueryService through the presenter."""

    KPI_DEFINITIONS = (
        ("active_employees", "Empleados activos", "Plantilla activa para el periodo actual", Icons.EMPLOYEE, "primary"),
        ("present_staff", "Personal presente", "Personas con jornada abierta o presente hoy", Icons.ATTENDANCE, "success"),
        ("absences_today", "Ausencias de hoy", "Ausencias detectadas para revisión", Icons.WARNING, "warning"),
        ("late_arrivals", "Retardos", "Entradas fuera de tolerancia", Icons.WARNING, "warning"),
        ("pending_requests", "Solicitudes pendientes", "Vacaciones, permisos o ajustes por aprobar", Icons.LEAVE, "info"),
        ("overtime_hours", "Horas extra", "Horas extra calculadas por dominio", Icons.SCHEDULE, "neutral"),
        ("estimated_payroll_cost", "Costo estimado de nómina", "Estimación provista por QueryService", Icons.PAYROLL, "neutral"),
        ("pending_incidents", "Incidencias pendientes", "Incidencias de asistencia sin resolver", Icons.WARNING, "danger"),
    )

    def __init__(self, presenter: HRPresenterPort, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        root = QVBoxLayout(self)
        root.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        root.setSpacing(DesktopSpacing.MD)
        root.addWidget(
            PageHeader(
                title="Resumen de Recursos Humanos",
                subtitle="Indicadores operativos calculados por el bounded context canónico de RRHH.",
                icon=Icons.HR,
                actions=(
                    PageAction(
                        text="Actualizar indicadores",
                        callback=self.refresh,
                        variant="primary",
                        tooltip="Recargar KPI desde HRDashboardQueryService.",
                    ),
                ),
                parent=self,
            )
        )
        self._loading = LoadingState(parent=self)
        root.addWidget(self._loading)
        self._empty = EmptyState("Sin indicadores para mostrar", "Los KPI aparecerán cuando HRDashboardQueryService entregue datos.", self)
        self._empty.setVisible(False)
        root.addWidget(self._empty)
        self._install_state_feedback(root)
        self._kpi_bar = KPIBar(
            tuple(
                KPIDTO(key=key, title=title, value="0", icon=icon, variant=variant, tooltip=tooltip)
                for key, title, tooltip, icon, variant in self.KPI_DEFINITIONS
            ),
            self,
            max_columns=4,
        )
        root.addWidget(self._kpi_bar)
        root.addStretch(1)
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
        self._kpi_bar.setVisible(False)
        self._empty.setVisible(False)
        self._error.setVisible(True)
        self._feedback.setText(message)
        self._feedback.setProperty("variant", "danger")
        self._feedback.setVisible(True)

    def refresh(self) -> None:
        self._loading.setVisible(True)
        self._hide_transient_states()
        try:
            self.render(self._presenter.load_dashboard())
            self._kpi_bar.setVisible(True)
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

    def render(self, kpi: HRDashboardKpiViewModel) -> None:
        self._kpi_bar.update_value("active_employees", str(kpi.active_employees))
        self._kpi_bar.update_value("present_staff", str(kpi.present_staff))
        self._kpi_bar.update_value("absences_today", str(kpi.absences_today))
        self._kpi_bar.update_value("late_arrivals", str(kpi.late_arrivals))
        self._kpi_bar.update_value("pending_requests", str(kpi.pending_requests))
        self._kpi_bar.update_value("overtime_hours", str(kpi.overtime_hours))
        self._kpi_bar.update_value("estimated_payroll_cost", str(kpi.estimated_payroll_cost))
        self._kpi_bar.update_value("pending_incidents", str(kpi.pending_incidents))
