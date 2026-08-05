"""Thin CASH-5 configuration UI; no persistence or business rules."""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable


class CashConfigurationPage(QWidget):
    create_requested = pyqtSignal(str)
    edit_requested = pyqtSignal(str, str)

    SECTIONS = (
        ("hierarchy", "Jerarquía"), ("validity", "Vigencias"),
        ("denominations", "Denominaciones"), ("payment_methods", "Medios de pago"),
        ("limits", "Límites"), ("alerts", "Alertas"),
        ("whatsapp", "WhatsApp"), ("permissions", "Permisos"),
    )

    def __init__(self, query_service, parent=None) -> None:
        super().__init__(parent)
        self._query = query_service
        self._tables = {}
        root = QVBoxLayout(self)
        add_button = create_primary_button(self, "Nueva configuración")
        refresh_button = create_secondary_button(self, "Actualizar")
        add_button.clicked.connect(self._request_create)
        refresh_button.clicked.connect(self.refresh)
        root.addWidget(PageHeader(
            self, title="Configuración de Caja",
            subtitle="Jerarquía, vigencias y políticas operativas por alcance.",
            actions=[refresh_button, add_button]))
        self._tabs = QTabWidget(self)
        self._tabs.setObjectName("cashConfigurationTabs")
        for section, label in self.SECTIONS:
            table = StandardTable([
                ColumnSpec("Nombre"), ColumnSpec("Valor"), ColumnSpec("Alcance", "status"),
                ColumnSpec("Vigente desde", "date"), ColumnSpec("Vigente hasta", "date"),
                ColumnSpec("Estado", "status"),
            ], self)
            table.doubleClicked.connect(lambda _index, key=section: self._request_edit(key))
            self._tables[section] = table
            self._tabs.addTab(table, label)
        root.addWidget(self._tabs)

    def _active_section(self) -> str:
        return self.SECTIONS[self._tabs.currentIndex()][0]

    def _request_create(self) -> None:
        self.create_requested.emit(self._active_section())

    def _request_edit(self, section: str) -> None:
        row_id = self._tables[section].selected_row_id()
        if row_id:
            self.edit_requested.emit(section, row_id)

    def refresh(self) -> None:
        for section, _label in self.SECTIONS:
            rows = self._query.list_section(section)
            self._tables[section].load_rows([
                [row.name, row.value, row.scope, row.effective_from,
                 row.effective_to, row.status] for row in rows
            ], row_ids=[row.id for row in rows])
