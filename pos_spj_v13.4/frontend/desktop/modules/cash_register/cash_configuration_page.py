"""Thin CASH-5 configuration UI; no persistence or business rules.

Cada pestaña es un catálogo que Caja LEE al operar (re-auditoría 2026-10-07):
se retiraron Jerarquía/Vigencias (nadie leía `cash_settings`), Permisos (se
administran en Usuarios y Roles) y Medios de pago (la clasificación vive en el
dominio de liquidación, no en esta tabla).
"""
from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox, QTabWidget, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.modules.cash_register.cash_register_dialogs import (
    CashAlertRecipientDialog,
    CashCatalogDialog,
)
from frontend.desktop.modules.cash_register.presentation import (
    catalog_row_text,
    scope_label,
    status_label,
    user_facing_error,
)


class CashConfigurationPage(QWidget):
    SECTIONS = (
        ("denominations", "Denominaciones"),
        ("reasons", "Motivos"),
        ("limits", "Límites"),
        ("tolerances", "Tolerancias"),
        ("alerts", "Avisos"),
        ("recipients", "Destinatarios"),
    )
    #: Todas las pestañas tienen alta y baja (avisos y destinatarios desde
    #: CASH-26 bloque 2: antes eran de sólo lectura y ningún aviso llegaba).
    EDITABLE = frozenset({"denominations", "reasons", "limits", "tolerances", "alerts",
                          "recipients"})

    def __init__(self, query_service, parent=None, *, presenter=None) -> None:
        super().__init__(parent)
        self._query = query_service
        self._presenter = presenter
        self._tables = {}
        root = QVBoxLayout(self)
        self._add_button = create_primary_button(self, "Nuevo")
        self._deactivate_button = create_secondary_button(self, "Dar de baja")
        refresh_button = create_secondary_button(self, "Actualizar")
        self._add_button.clicked.connect(self._request_create)
        self._deactivate_button.clicked.connect(self._request_deactivate)
        refresh_button.clicked.connect(self.refresh)
        apply_tooltip(self._deactivate_button,
                      "Cierra la vigencia del registro seleccionado; el historial se conserva.")
        root.addWidget(PageHeader(
            self, title="Configuración de Caja",
            subtitle="Catálogos que Caja aplica al operar y a quién avisa cuando algo sale mal.",
            actions=[refresh_button, self._deactivate_button, self._add_button]))
        self._tabs = QTabWidget(self)
        self._tabs.setObjectName("cashConfigurationTabs")
        for section, label in self.SECTIONS:
            table = StandardTable([
                ColumnSpec("Nombre"), ColumnSpec("Valor"), ColumnSpec("Aplica a", "status"),
                ColumnSpec("Vigente desde", "date"), ColumnSpec("Vigente hasta", "date"),
                ColumnSpec("Estado", "status"),
            ], self)
            self._tables[section] = table
            self._tabs.addTab(table, label)
        self._tabs.currentChanged.connect(self._sync_actions)
        root.addWidget(self._tabs)
        self._sync_actions()

    def _active_section(self) -> str:
        return self.SECTIONS[self._tabs.currentIndex()][0]

    def _sync_actions(self, _index: int = 0) -> None:
        editable = self._active_section() in self.EDITABLE and self._presenter is not None
        self._add_button.setEnabled(editable)
        self._deactivate_button.setEnabled(editable)
        apply_tooltip(self._add_button, "Agregar un registro a este catalogo.")

    def _request_create(self) -> None:
        section = self._active_section()
        if self._presenter is None or section not in self.EDITABLE:
            return
        if section == "recipients":
            dialog = CashAlertRecipientDialog(
                self, alerts=self._presenter.alert_rule_options(),
                users=self._presenter.alert_user_options())
        else:
            dialog = CashCatalogDialog(self, section=section)
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            if section == "recipients":
                result = self._presenter.add_cash_alert_recipient(**dialog.result_fields())
            else:
                result = self._presenter.configure_cash_catalog(
                    section=section, fields=dialog.result_fields())
        except Exception as exc:  # noqa: BLE001 - se muestra al usuario
            QMessageBox.warning(self, "Caja", user_facing_error(exc))
            return
        QMessageBox.information(self, "Caja", getattr(result, "message", "Configuracion guardada"))
        self.refresh()

    def _request_deactivate(self) -> None:
        section = self._active_section()
        row_id = self._tables[section].selected_row_id()
        if self._presenter is None or section not in self.EDITABLE:
            return
        if not row_id:
            QMessageBox.information(self, "Caja", "Selecciona el registro que quieres dar de baja.")
            return
        try:
            if section == "recipients":
                result = self._presenter.deactivate_cash_alert_recipient(row_id=row_id)
            else:
                result = self._presenter.deactivate_cash_configuration(
                    section=section, row_id=row_id)
        except Exception as exc:  # noqa: BLE001 - se muestra al usuario
            QMessageBox.warning(self, "Caja", user_facing_error(exc))
            return
        QMessageBox.information(self, "Caja", getattr(result, "message", "Registro dado de baja"))
        self.refresh()

    def refresh(self) -> None:
        for section, _label in self.SECTIONS:
            rows = self._query.list_section(section)
            self._tables[section].load_rows([
                [*catalog_row_text(section, row.name, row.value), scope_label(row.scope),
                 row.effective_from, row.effective_to, status_label(row.status)] for row in rows
            ], row_ids=[row.id for row in rows])
