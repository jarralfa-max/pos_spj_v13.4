"""Canonical HR desktop view with internal side navigation."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QStackedWidget, QWidget

from frontend.desktop.modules.hr.hr_presenter import HRPresenterPort
from frontend.desktop.modules.hr.pages.attendance_page import HRAttendancePage
from frontend.desktop.modules.hr.pages.employees_page import HREmployeesPage
from frontend.desktop.modules.hr.pages.evaluations_page import HREvaluationsPage
from frontend.desktop.modules.hr.pages.leave_page import HRLeavePage
from frontend.desktop.modules.hr.pages.overview_page import HROverviewPage
from frontend.desktop.modules.hr.pages.payroll_page import HRPayrollPage
from frontend.desktop.modules.hr.pages.schedules_page import HRSchedulesPage
from frontend.desktop.modules.hr.pages.settings_page import HRSettingsPage
<<<<<<< HEAD
=======
from frontend.desktop.components import Tooltip
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
from frontend.desktop.themes import DesktopSpacing


class HRView(QWidget):
    """Top-level RRHH view that delegates reads/actions to the presenter."""

    MINIMUM_WIDTH_FOR_1366 = 1024
    MINIMUM_HEIGHT_FOR_768 = 640
<<<<<<< HEAD
=======
    VALIDATED_RESOLUTIONS = ((1366, 768), (1440, 900), (1920, 1080))
    ACCESSIBILITY_SCALE_MIN = 1.0
    ACCESSIBILITY_SCALE_MAX = 2.0
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23

    def __init__(self, presenter: HRPresenterPort, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self.setMinimumSize(self.MINIMUM_WIDTH_FOR_1366, self.MINIMUM_HEIGHT_FOR_768)
<<<<<<< HEAD
=======
        self.setAccessibleName("Módulo de Recursos Humanos")
        self.setAccessibleDescription("Vista responsive de RRHH validada para 1366x768, 1440x900 y 1920x1080.")
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
        layout = QHBoxLayout(self)
        layout.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        layout.setSpacing(DesktopSpacing.MD)

        self._navigation = QListWidget(self)
        self._navigation.setObjectName("hrSecondaryNavigation")
        self._navigation.setAccessibleName("Navegación secundaria de Recursos Humanos")
        self._navigation.setMinimumWidth(220)
        self._navigation.setMaximumWidth(280)
<<<<<<< HEAD
        self._navigation.setToolTip("Use esta navegación para cambiar entre áreas de RRHH")
=======
        Tooltip.attach(
            self._navigation,
            title="Navegación RRHH",
            description="Use las flechas del teclado o clic para cambiar entre áreas de Recursos Humanos.",
        )
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
        self._stack = QStackedWidget(self)
        layout.addWidget(self._navigation)
        layout.addWidget(self._stack, 1)

        self._add_page("Resumen", "Indicadores principales de Recursos Humanos", HROverviewPage(self._presenter, self))
        self._add_page("Personal", "Administración de empleados", HREmployeesPage(self._presenter, self))
        self._add_page("Asistencia", "Marcaciones, jornadas e incidencias", HRAttendancePage(self._presenter, self))
        self._add_page("Turnos", "Turnos laborales y asignaciones", HRSchedulesPage(presenter, self))
        self._add_page("Vacaciones y permisos", "Solicitudes, saldos y autorizaciones", HRLeavePage(presenter, self))
        self._add_page("Nómina", "Corridas, autorizaciones y pagos", HRPayrollPage(presenter, self))
        self._add_page("Evaluaciones", "Evaluaciones de desempeño", HREvaluationsPage(self))
        self._add_page("Configuración", "Catálogos y políticas de RRHH", HRSettingsPage(self))
        self._navigation.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._navigation.setCurrentRow(0)

    def _add_page(self, label: str, tooltip: str, page: QWidget) -> None:
        item = QListWidgetItem(label)
        item.setToolTip(tooltip)
<<<<<<< HEAD
=======
        item.setData(Qt.UserRole, label)
        item.setData(Qt.UserRole + 1, tooltip)
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._navigation.addItem(item)
        self._stack.addWidget(page)

    def refresh(self) -> None:
        current = self._stack.currentWidget()
        refresh = getattr(current, "refresh", None)
        if callable(refresh):
            refresh()
