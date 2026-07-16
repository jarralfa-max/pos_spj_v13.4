"""HRView — main HR module view (navigation + lazy pages).

Receives a fully wired ``HRPresenter``; never touches the database, the app
container, SQL or business rules.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.modules.hr.pages.adjustments_page import AdjustmentsPage
from frontend.desktop.modules.hr.pages.attendance_page import AttendancePage
from frontend.desktop.modules.hr.pages.employees_page import EmployeesPage
from frontend.desktop.modules.hr.pages.evaluations_page import EvaluationsPage
from frontend.desktop.modules.hr.pages.leave_page import LeavePage
from frontend.desktop.modules.hr.pages.overview_page import OverviewPage
from frontend.desktop.modules.hr.pages.payroll_page import PayrollPage
from frontend.desktop.modules.hr.pages.schedules_page import SchedulesPage
from frontend.desktop.modules.hr.pages.settings_page import SettingsPage

#: (section label or None, page label, page class)
_NAVIGATION = [
    (None, "Resumen", OverviewPage),
    ("Personal", "Empleados", EmployeesPage),
    ("Asistencia", "Jornadas", AttendancePage),
    ("Asistencia", "Ajustes", AdjustmentsPage),
    ("Horarios", "Turnos", SchedulesPage),
    ("Ausencias", "Vacaciones y permisos", LeavePage),
    ("Nómina", "Corridas de nómina", PayrollPage),
    ("Desempeño", "Evaluaciones", EvaluationsPage),
    (None, "Configuración", SettingsPage),
]


class HRView(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self.setObjectName("hrModule")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._nav = QListWidget(self)
        self._nav.setObjectName("hrNav")
        self._nav.setMaximumWidth(260)
        self._nav.setMinimumWidth(220)

        self._stack = QStackedWidget(self)
        self._pages: list = []
        self._build_navigation()

        layout.addWidget(self._nav)
        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self._stack)
        layout.addWidget(content, stretch=1)

        self._nav.currentRowChanged.connect(self._on_nav_changed)
        self._nav.setCurrentRow(self._first_page_row)

    def _build_navigation(self) -> None:
        current_section = object()
        self._row_to_page_index: dict[int, int] = {}
        self._first_page_row = 0
        first_set = False
        for section, label, page_class in _NAVIGATION:
            if section is not None and section != current_section:
                header_item = QListWidgetItem(section.upper())
                header_item.setFlags(Qt.NoItemFlags)
                self._nav.addItem(header_item)
            current_section = section if section is not None else current_section
            item = QListWidgetItem(f"  {label}")
            self._nav.addItem(item)
            page = page_class(self._presenter, self)
            self._stack.addWidget(page)
            self._pages.append(page)
            row = self._nav.count() - 1
            self._row_to_page_index[row] = len(self._pages) - 1
            if not first_set:
                self._first_page_row = row
                first_set = True

    def _on_nav_changed(self, row: int) -> None:
        page_index = self._row_to_page_index.get(row)
        if page_index is None:
            return
        self._stack.setCurrentIndex(page_index)
        self._pages[page_index].ensure_loaded()

    def set_active_submodule(self, name: str) -> None:
        """Compatibility hook for legacy deep links (e.g. 'turnos', 'nomina')."""
        targets = {"turnos": SchedulesPage, "nomina": PayrollPage,
                   "asistencia": AttendancePage, "empleados": EmployeesPage}
        page_class = targets.get(str(name or "").lower())
        if page_class is None:
            return
        for index, page in enumerate(self._pages):
            if isinstance(page, page_class):
                for row, mapped in self._row_to_page_index.items():
                    if mapped == index:
                        self._nav.setCurrentRow(row)
                        return
