"""AttributeFormDialog + AttributeOptionsDialog — atributos y opciones (P1-03).

UI-only: captura atributo (nombre/código automático reescribible/tipo) y gestiona sus opciones enumeradas.
El tipo de dato sólo se elige al crear (inmutable después). Delega en el presenter.
"""

from __future__ import annotations

from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.modules.products.dialogs.auto_code import (
    AutoCodeBinder,
    catalog_suggester,
)

from PyQt5.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
)

from frontend.desktop.components import ColumnSpec, StandardTable

_DATA_TYPES = (
    ("LIST", "Lista de opciones"),
    ("TEXT", "Texto"),
    ("NUMBER", "Número"),
    ("BOOLEAN", "Sí / No"),
)


class AttributeFormDialog(StandardDialog):
    def __init__(self, presenter, *, attribute=None, parent=None) -> None:
        super().__init__(parent, width=420)
        self._presenter = presenter
        self._attribute = attribute or {}
        self._attribute_id = self._attribute.get("id")
        self.setObjectName("attributeFormDialog")
        self.setWindowTitle("Editar atributo" if self._attribute_id
                            else "Nuevo atributo")
        self.setMinimumWidth(420)

        layout = self.content_layout()
        form = QFormLayout()
        self.code = QLineEdit(str(self._attribute.get("code") or ""))
        self.name = QLineEdit(str(self._attribute.get("name") or ""))
        self.data_type = QComboBox()
        for value, label in _DATA_TYPES:
            self.data_type.addItem(label, value)
        if self._attribute_id:
            # El tipo es inmutable tras el alta.
            self._select(self.data_type, self._attribute.get("data_type"))
            self.data_type.setEnabled(False)
        form.addRow("Nombre *", self.name)
        form.addRow("Código" if self._attribute_id is None else "Código *", self.code)
        form.addRow("Tipo *", self.data_type)
        # PROD-23: en el alta el código se genera del nombre (reescribible).
        self._auto = (AutoCodeBinder(self.name, self.code, catalog_suggester(
            self._presenter, "ATTRIBUTE"))
            if self._attribute_id is None else None)
        layout.addLayout(form)

        self._error = QLabel()
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        self.add_footer_widget(buttons)

    @staticmethod
    def _select(combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _on_save(self) -> None:
        self._error.setText("")
        code = (self._auto.code_for_save() if self._auto is not None
                else self.code.text().strip().upper())
        name = self.name.text().strip()
        if not name or (self._auto is None and not code):
            self._error.setText("Nombre es obligatorio." if self._auto is not None
                                else "Código y Nombre son obligatorios.")
            return
        ok, message, _aid = self._presenter.save_attribute(
            attribute_id=self._attribute_id, code=code, name=name,
            data_type=self.data_type.currentData())
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            QMessageBox.warning(self, "No se pudo guardar", message)


class _OptionEditor(StandardDialog):
    def __init__(self, presenter, *, attribute_id, option=None, parent=None) -> None:
        super().__init__(parent, width=360)
        self._presenter = presenter
        self._attribute_id = attribute_id
        self._option = option or {}
        self._option_id = self._option.get("id")
        self.setWindowTitle("Editar opción" if self._option_id else "Nueva opción")
        self.setMinimumWidth(360)

        layout = self.content_layout()
        form = QFormLayout()
        self.code = QLineEdit(str(self._option.get("code") or ""))
        self.label = QLineEdit(str(self._option.get("label") or ""))
        self.sort_order = QSpinBox()
        self.sort_order.setRange(0, 9999)
        self.sort_order.setValue(int(self._option.get("sort_order") or 0))
        form.addRow("Etiqueta *", self.label)
        form.addRow("Código" if self._option_id is None else "Código *", self.code)
        form.addRow("Orden", self.sort_order)
        # PROD-23: código de la opción desde la etiqueta (único en el atributo).
        self._auto = (AutoCodeBinder(self.label, self.code, catalog_suggester(
            self._presenter, "ATTRIBUTE_OPTION", scope_id=self._attribute_id))
            if self._option_id is None else None)
        layout.addLayout(form)

        self._error = QLabel()
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        self.add_footer_widget(buttons)

    def _on_save(self) -> None:
        self._error.setText("")
        code = (self._auto.code_for_save() if self._auto is not None
                else self.code.text().strip().upper())
        label = self.label.text().strip()
        if not label or (self._auto is None and not code):
            self._error.setText("Etiqueta es obligatoria." if self._auto is not None
                                else "Código y Etiqueta son obligatorios.")
            return
        ok, message, _oid = self._presenter.save_attribute_option(
            option_id=self._option_id, attribute_id=self._attribute_id, code=code,
            label=label, sort_order=self.sort_order.value(),
            active=bool(self._option.get("active", True)))
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            QMessageBox.warning(self, "No se pudo guardar", message)


class AttributeOptionsDialog(StandardDialog):
    """Lista y edita las opciones de un atributo de tipo LISTA."""

    def __init__(self, presenter, *, attribute, parent=None) -> None:
        super().__init__(parent, width=480)
        self._presenter = presenter
        self._attribute = attribute
        self._attribute_id = attribute["id"]
        self._is_list = attribute.get("data_type") == "LIST"
        self.setObjectName("attributeOptionsDialog")
        self.setWindowTitle(f"Opciones de «{attribute.get('name')}»")
        self.setMinimumSize(480, 360)

        layout = self.content_layout()
        toolbar = QHBoxLayout()
        self.btn_new = QPushButton("Nueva opción")
        self.btn_edit = QPushButton("Editar")
        can_manage = bool(getattr(self._presenter, "can_manage_attributes", False))
        for b in (self.btn_new, self.btn_edit):
            b.setEnabled(can_manage and self._is_list)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.btn_new.clicked.connect(lambda: self._edit(None))
        self.btn_edit.clicked.connect(self._edit_selected)

        if not self._is_list:
            layout.addWidget(QLabel("Este tipo de atributo no usa opciones enumeradas."))

        self.table = StandardTable(columns=[
            ColumnSpec("Código", "code"),
            ColumnSpec("Etiqueta", "label"),
            ColumnSpec("Orden", "sort_order"),
            ColumnSpec("Estado", "estado"),
        ])
        layout.addWidget(self.table, 1)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.button(QDialogButtonBox.Close).setText("Cerrar")
        close.rejected.connect(self.reject)
        close.accepted.connect(self.accept)
        self.add_footer_widget(close)
        self.refresh()

    def refresh(self) -> None:
        options = self._presenter.list_attribute_options(self._attribute_id)
        rows = [[o["code"], o["label"], str(o.get("sort_order") or 0),
                 "Activa" if o.get("active") else "Inactiva"] for o in options]
        self.table.load_rows(rows, row_ids=[o["id"] for o in options])

    def _edit_selected(self) -> None:
        option_id = self.table.selected_row_id()
        if not option_id:
            return
        options = self._presenter.list_attribute_options(self._attribute_id)
        option = next((o for o in options if o["id"] == option_id), None)
        self._edit(option)

    def _edit(self, option) -> None:
        dlg = _OptionEditor(self._presenter, attribute_id=self._attribute_id,
                            option=option, parent=self)
        if dlg.exec_():
            self.refresh()
