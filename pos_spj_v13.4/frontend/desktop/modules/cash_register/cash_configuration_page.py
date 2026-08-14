"""Thin CASH-5 configuration UI; no persistence or business rules."""
from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox, QTabWidget, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.cash_register.cash_register_dialogs import CashConfigurationDialog
from frontend.desktop.modules.cash_register.presentation import scope_label, status_label, user_facing_error


class CashConfigurationPage(QWidget):
    SECTIONS = (
        ("hierarchy", "Jerarquía"), ("validity", "Vigencias"),
        ("denominations", "Denominaciones"), ("payment_methods", "Medios de pago"),
        ("limits", "Límites"), ("alerts", "Alertas"),
        ("whatsapp", "WhatsApp"), ("permissions", "Permisos"),
    )

    def __init__(self, query_service, parent=None, *, presenter=None) -> None:
        super().__init__(parent)
        self._query = query_service
        self._presenter = presenter
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
        if self._presenter is None:
            QMessageBox.warning(self, "Caja", "Comando de configuracion no disponible.")
            return
        section = self._active_section()
        dialog = CashConfigurationDialog(self, section=section)
        if dialog.exec_() != dialog.Accepted:
            return
        value = dialog.result_value()
        try:
            result = self._presenter.configure_cash_register(
                section=section,
                name=value.name,
                value=value.value,
                scope_type=value.scope_type,
                scope_id=value.scope_id,
                effective_from=value.effective_from,
                effective_to=value.effective_to,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Caja", user_facing_error(exc))
            return
        QMessageBox.information(self, "Caja", getattr(result, "message", "Configuracion guardada"))
        self.refresh()

    def _request_edit(self, section: str) -> None:
        row_id = self._tables[section].selected_row_id()
        if row_id:
            QMessageBox.information(
                self,
                "Caja",
                "La edicion conserva vigencias: crea una nueva configuracion efectiva "
                "para reemplazar la seleccion actual.",
            )
            self._tabs.setCurrentIndex([key for key, _ in self.SECTIONS].index(section))
            self._request_create()

    def refresh(self) -> None:
        for section, _label in self.SECTIONS:
            rows = self._query.list_section(section)
            self._tables[section].load_rows([
                [row.name, row.value, scope_label(row.scope), row.effective_from,
                 row.effective_to, status_label(row.status)] for row in rows
            ], row_ids=[row.id for row in rows])
