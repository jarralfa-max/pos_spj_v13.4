"""Atributos de producto — gestión del catálogo configurable (P1-03).

UI only: una StandardTable de atributos y una barra de acciones (nuevo, editar,
opciones, activar/desactivar). Las opciones enumeradas se editan en un diálogo
aparte. Toda mutación pasa por el presenter → use cases canónicos.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing

_TYPE_ES = {"LIST": "Lista", "TEXT": "Texto", "NUMBER": "Número", "BOOLEAN": "Sí/No"}


class ProductAttributesPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productAttributesPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Atributos",
            subtitle="Atributos configurables (color, talla…) y sus opciones para "
                     "clasificar y generar variantes.",
            icon=getattr(Icons, "CATALOG", None), compact=True)
        layout.addWidget(self.header)

        toolbar = QHBoxLayout()
        self.btn_new = QPushButton("Nuevo atributo")
        self.btn_edit = QPushButton("Editar")
        self.btn_options = QPushButton("Opciones")
        self.btn_toggle = QPushButton("Activar/Desactivar")
        can_manage = bool(getattr(self._presenter, "can_manage_attributes", False))
        for b in (self.btn_new, self.btn_edit, self.btn_options, self.btn_toggle):
            toolbar.addWidget(b)
        for b in (self.btn_new, self.btn_edit, self.btn_toggle):
            b.setEnabled(can_manage)
        self.btn_options.setEnabled(True)  # ver opciones siempre; editar según permiso
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.btn_new.clicked.connect(lambda: self._open_form(None))
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_options.clicked.connect(self._open_options)
        self.btn_toggle.clicked.connect(self._toggle_selected)

        self.table = StandardTable(columns=[
            ColumnSpec("Código", "code"),
            ColumnSpec("Nombre", "name"),
            ColumnSpec("Tipo", "tipo"),
            ColumnSpec("Estado", "estado"),
        ])
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        attrs = self._presenter.attribute_catalog()
        rows = [[a["code"], a["name"], _TYPE_ES.get(a["data_type"], a["data_type"]),
                 "Activo" if a.get("active") else "Inactivo"] for a in attrs]
        self.table.load_rows(rows, row_ids=[a["id"] for a in attrs])

    def _edit_selected(self) -> None:
        attribute_id = self.table.selected_row_id()
        if attribute_id:
            self._open_form(self._presenter.get_attribute(attribute_id))

    def _open_form(self, attribute) -> None:
        from frontend.desktop.modules.products.dialogs.attribute_form_dialog import (
            AttributeFormDialog,
        )
        dialog = AttributeFormDialog(self._presenter, attribute=attribute, parent=self)
        if dialog.exec_():
            self.refresh()

    def _open_options(self) -> None:
        attribute_id = self.table.selected_row_id()
        if not attribute_id:
            return
        attribute = self._presenter.get_attribute(attribute_id)
        if attribute is None:
            return
        from frontend.desktop.modules.products.dialogs.attribute_form_dialog import (
            AttributeOptionsDialog,
        )
        AttributeOptionsDialog(self._presenter, attribute=attribute, parent=self).exec_()

    def _toggle_selected(self) -> None:
        attribute_id = self.table.selected_row_id()
        if not attribute_id:
            return
        row = self._presenter.get_attribute(attribute_id)
        if row is None:
            return
        self._presenter.set_attribute_active(attribute_id, not bool(row.get("active")))
        self.refresh()
