"""TemplatesPage (LOY-25, route ``tarjetas.templates``) — create a
template, add a design version (raw JSON, validated by LOY-18's own
allowlist on the backend), and approve/activate it.

No visual Studio exists yet (LOY-18 only built the declarative schema
CONTRACT and its validator, never a drag-and-drop editor) — this page
accepts the design schema as raw JSON text, which the backend rejects
outright if it doesn't satisfy the closed allowlist (unknown element
types, disallowed placeholders, HTML content, etc.). A pre-filled minimal
valid example is provided so an operator has a real starting point.
"""

from __future__ import annotations

import json

from PyQt5.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from frontend.desktop.components import FormField, StandardForm
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.tokens import Spacing

_EXAMPLE_SCHEMA = json.dumps({
    "canvas": {"width_mm": "85.6", "height_mm": "54", "background_color": "#FFFFFF"},
    "elements": [
        {"type": "TEXT", "x_mm": "5", "y_mm": "5", "width_mm": "50", "height_mm": "8",
         "content": "{{customer_name}}"},
        {"type": "QR", "x_mm": "60", "y_mm": "5", "width_mm": "20", "height_mm": "20",
         "data_source": "CARD_TOKEN"},
    ],
}, indent=2, ensure_ascii=False)


class TemplatesPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("tarjetasFidelidadTemplatesPage")
        self._presenter = presenter
        self._current_template_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        layout.addWidget(QLabel("Crear plantilla", self))
        self._create_form = StandardForm(self)
        self._code_input = StandardLineEdit(self)
        self._create_form.add_field("code", FormField("Código", self._code_input, required=True))
        self._name_input = StandardLineEdit(self)
        self._create_form.add_field("name", FormField("Nombre", self._name_input, required=True))
        layout.addWidget(self._create_form)
        create_btn = create_primary_button(self, "Crear plantilla")
        create_btn.clicked.connect(self._create_template)
        layout.addWidget(create_btn)

        approve_btn = create_secondary_button(self, "Aprobar plantilla creada")
        approve_btn.clicked.connect(self._approve_template)
        layout.addWidget(approve_btn)

        layout.addWidget(QLabel(
            "Crear versión de diseño (JSON, validado por el backend)", self))
        self._design_schema_input = QPlainTextEdit(self)
        self._design_schema_input.setPlainText(_EXAMPLE_SCHEMA)
        self._design_schema_input.setObjectName("tarjetasFidelidadDesignSchemaInput")
        layout.addWidget(self._design_schema_input)
        create_version_btn = create_secondary_button(self, "Crear versión")
        create_version_btn.clicked.connect(self._create_version)
        layout.addWidget(create_version_btn)

        self._version_id_input = StandardLineEdit(self)
        self._version_id_input.setPlaceholderText("ID de la versión")
        layout.addWidget(self._version_id_input)
        version_actions = QVBoxLayout()
        approve_version_btn = create_secondary_button(self, "Aprobar versión")
        approve_version_btn.clicked.connect(self._approve_version)
        version_actions.addWidget(approve_version_btn)
        activate_version_btn = create_primary_button(self, "Activar versión")
        activate_version_btn.clicked.connect(self._activate_version)
        version_actions.addWidget(activate_version_btn)
        layout.addLayout(version_actions)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        pass

    def _create_template(self) -> None:
        errors = {}
        if not self._code_input.text().strip():
            errors["code"] = "Obligatorio"
        if not self._name_input.text().strip():
            errors["name"] = "Obligatorio"
        self._create_form.set_errors(errors)
        if errors:
            return
        result = self._presenter.create_template(
            code=self._code_input.text().strip(), name=self._name_input.text().strip())
        if result.success:
            self._current_template_id = result.entity_id
        self._show_message(result.message, error=not result.success)

    def _approve_template(self) -> None:
        if not self._current_template_id:
            self._show_message("Crea una plantilla primero.", error=True)
            return
        result = self._presenter.approve_template(self._current_template_id)
        self._show_message(result.message, error=not result.success)

    def _create_version(self) -> None:
        if not self._current_template_id:
            self._show_message("Crea una plantilla primero.", error=True)
            return
        design_schema_json = self._design_schema_input.toPlainText().strip()
        if not design_schema_json:
            self._show_message("El esquema de diseño es obligatorio.", error=True)
            return
        result = self._presenter.create_template_version(
            template_id=self._current_template_id, design_schema_json=design_schema_json)
        if result.success:
            self._version_id_input.setText(result.entity_id)
        self._show_message(result.message, error=not result.success)

    def _approve_version(self) -> None:
        version_id = self._version_id_input.text().strip()
        if not version_id:
            self._show_message("Ingresa el ID de la versión.", error=True)
            return
        result = self._presenter.approve_template_version(version_id)
        self._show_message(result.message, error=not result.success)

    def _activate_version(self) -> None:
        version_id = self._version_id_input.text().strip()
        if not version_id:
            self._show_message("Ingresa el ID de la versión.", error=True)
            return
        result = self._presenter.activate_template_version(version_id)
        self._show_message(result.message, error=not result.success)

    def _show_message(self, message: str, *, error: bool) -> None:
        self._status.setProperty("state", "ERROR" if error else "READY")
        self._status.setText(message)
        self._status.show()
