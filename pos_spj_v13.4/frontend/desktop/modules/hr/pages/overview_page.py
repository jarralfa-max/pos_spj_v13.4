"""HR dashboard overview page."""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import Icons, KPIBar, KPIDTO, LoadingState, PageAction, PageHeader
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

    def refresh(self) -> None:
        self._loading.setVisible(True)
        try:
            self.render(self._presenter.load_dashboard())
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
