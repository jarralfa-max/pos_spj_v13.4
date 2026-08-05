"""CASH-6 device administration UI; backend owns every mutation."""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable


class CashDevicesPage(QWidget):
    create_requested = pyqtSignal(str)
    action_requested = pyqtSignal(str, str, str)
    SECTIONS = (("register", "Cajas"), ("drawer", "Cajones"), ("terminal", "Terminales"))

    def __init__(self, query_service, parent=None):
        super().__init__(parent)
        self._query, self._tables = query_service, {}
        root = QVBoxLayout(self)
        create = create_primary_button(self, "Nuevo dispositivo")
        refresh = create_secondary_button(self, "Actualizar")
        create.clicked.connect(lambda: self.create_requested.emit(self._active_kind()))
        refresh.clicked.connect(self.refresh)
        root.addWidget(PageHeader(self, title="Cajas, cajones y terminales",
                                  subtitle="Administración, asignación y estado del hardware de Caja.",
                                  actions=[refresh, create]))
        self._tabs = QTabWidget(self)
        for kind, label in self.SECTIONS:
            table = StandardTable([ColumnSpec("Nombre"), ColumnSpec("Sucursal"),
                                   ColumnSpec("Asignación"), ColumnSpec("Estado", "status"),
                                   ColumnSpec("Hardware", "status")], self)
            table.doubleClicked.connect(lambda _index, key=kind: self._emit_edit(key))
            self._tables[kind] = table
            self._tabs.addTab(table, label)
        root.addWidget(self._tabs)

    def _active_kind(self): return self.SECTIONS[self._tabs.currentIndex()][0]
    def _emit_edit(self, kind):
        entity_id = self._tables[kind].selected_row_id()
        if entity_id: self.action_requested.emit(kind, entity_id, "EDIT")

    def refresh(self):
        for kind, _label in self.SECTIONS:
            rows = self._query.list_devices(kind)
            self._tables[kind].load_rows(
                [[row.name, row.branch_name, row.assignment, row.status, row.hardware_status] for row in rows],
                row_ids=[row.id for row in rows])
