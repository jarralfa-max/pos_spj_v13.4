"""HR dashboard overview page."""

from __future__ import annotations

from PyQt5.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from frontend.desktop.components import LoadingState
from frontend.desktop.modules.hr.hr_presenter import HRPresenterPort
from frontend.desktop.modules.hr.hr_view_models import HRDashboardKpiViewModel
from frontend.desktop.themes import DesktopSpacing


class HROverviewPage(QWidget):
    """Dashboard page: all KPI values come from HRDashboardQueryService through the presenter."""

    KPI_LABELS = (
        ("active_employees", "Empleados activos", "Plantilla activa para el periodo actual"),
        ("present_staff", "Personal presente", "Personas con jornada abierta o presente hoy"),
        ("absences_today", "Ausencias de hoy", "Ausencias detectadas para revisión"),
        ("late_arrivals", "Retardos", "Entradas fuera de tolerancia"),
        ("pending_requests", "Solicitudes pendientes", "Vacaciones, permisos o ajustes por aprobar"),
        ("overtime_hours", "Horas extra", "Horas extra calculadas por dominio"),
        ("estimated_payroll_cost", "Costo estimado de nómina", "Estimación provista por QueryService"),
        ("pending_incidents", "Incidencias pendientes", "Incidencias de asistencia sin resolver"),
    )

    def __init__(self, presenter: HRPresenterPort, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        root = QVBoxLayout(self)
        root.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        root.setSpacing(DesktopSpacing.MD)
        title = QLabel("Resumen de Recursos Humanos", self)
        title.setWordWrap(True)
        root.addWidget(title)
        refresh = QPushButton("Actualizar indicadores", self)
        refresh.setToolTip("Recargar KPI desde HRDashboardQueryService")
        refresh.clicked.connect(self.refresh)
        root.addWidget(refresh)
        self._loading = LoadingState(parent=self)
        root.addWidget(self._loading)
        grid = QGridLayout()
        grid.setSpacing(DesktopSpacing.MD)
        self._labels: dict[str, QLabel] = {}
        for index, (key, text, tooltip) in enumerate(self.KPI_LABELS):
            card = QWidget(self)
            card.setProperty("component", "kpiCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(DesktopSpacing.MD, DesktopSpacing.MD, DesktopSpacing.MD, DesktopSpacing.MD)
            name = QLabel(text, card)
            name.setWordWrap(True)
            value = QLabel("0", card)
            value.setAccessibleName(text)
            value.setToolTip(tooltip)
            self._labels[key] = value
            card_layout.addWidget(name)
            card_layout.addWidget(value)
            grid.addWidget(card, index // 4, index % 4)
        root.addLayout(grid)
        root.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        self._loading.setVisible(True)
        try:
            self.render(self._presenter.load_dashboard())
        finally:
            self._loading.setVisible(False)

    def render(self, kpi: HRDashboardKpiViewModel) -> None:
        self._labels["active_employees"].setText(str(kpi.active_employees))
        self._labels["present_staff"].setText(str(kpi.present_staff))
        self._labels["absences_today"].setText(str(kpi.absences_today))
        self._labels["late_arrivals"].setText(str(kpi.late_arrivals))
        self._labels["pending_requests"].setText(str(kpi.pending_requests))
        self._labels["overtime_hours"].setText(str(kpi.overtime_hours))
        self._labels["estimated_payroll_cost"].setText(str(kpi.estimated_payroll_cost))
        self._labels["pending_incidents"].setText(str(kpi.pending_incidents))
