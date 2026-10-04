"""Dialogs for the "Documentos" section — third real CRUD wired for
Configuración (SET-25 follow-up #3). Built entirely on `FormDialog`/
`ConfirmationDialog` (FASE DS-3), never a raw `QDialog`.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialogButtonBox

from frontend.desktop.components import (
    FormDialog,
    SearchableComboBox,
    StandardLineEdit,
    StandardTextArea,
    apply_tooltip,
)

from .document_type_labels import DOCUMENT_TYPE_LABELS

_DOCUMENT_TYPES = DOCUMENT_TYPE_LABELS

_RENDER_FORMATS = (
    ("ESC_POS", "ESC/POS (térmica)"), ("HTML", "HTML"), ("PDF", "PDF"), ("ZPL", "ZPL (etiquetas)"),
    ("VIRTUAL", "Virtual"),
)


class DocumentTemplateCreateDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nueva plantilla de documento")
        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre de la plantilla")
        self.form.addRow("Nombre:", self.name)

        self.document_type = SearchableComboBox(self, placeholder="Selecciona un tipo…")
        self.document_type.set_options(_DOCUMENT_TYPES)
        self.document_type.setAccessibleName("Tipo de documento")
        self.form.addRow("Tipo:", self.document_type)

        self.module = StandardLineEdit(self)
        self.module.setAccessibleName("Módulo dueño")
        apply_tooltip(self.module, "El bounded context dueño del contenido, ej. «ventas», «inventario».")
        self.form.addRow("Módulo:", self.module)

        self.description = StandardLineEdit(self)
        self.description.setAccessibleName("Descripción")
        self.form.addRow("Descripción:", self.description)

        self.content_format = SearchableComboBox(self, placeholder="Selecciona un formato…")
        self.content_format.set_options(_RENDER_FORMATS)
        self.content_format.setAccessibleName("Formato de renderizado")
        self.form.addRow("Formato:", self.content_format)

        self.content = StandardTextArea(self)
        self.content.setAccessibleName("Contenido de la plantilla")
        apply_tooltip(self.content, "Plantilla con placeholders — nunca datos ya renderizados (§27).")
        self.form.addRow("Contenido:", self.content)

        self.add_button_box(ok_text="Crear plantilla")

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(), "document_type": self.document_type.current_id(),
            "module": self.module.text().strip(), "description": self.description.text().strip(),
            "content_format": self.content_format.current_id(), "content": self.content.toPlainText().strip(),
        }


class DocumentTemplateEditDialog(FormDialog):
    """Edits a `DocumentTemplate` family's name/module/description —
    never its `document_type` or versioned content (that's
    `NewTemplateVersionDialog`'s job). SET-11 follow-up: the domain had
    no way to do this at all before `DocumentTemplate.update_details()`."""

    def __init__(self, parent=None, *, name: str = "", module: str = "", description: str = "") -> None:
        super().__init__(parent, title="Editar plantilla")
        self.name = StandardLineEdit(self)
        self.name.setText(name)
        self.name.setAccessibleName("Nombre de la plantilla")
        self.form.addRow("Nombre:", self.name)

        self.module = StandardLineEdit(self)
        self.module.setText(module)
        self.module.setAccessibleName("Módulo dueño")
        apply_tooltip(self.module, "El bounded context dueño del contenido, ej. «ventas», «inventario».")
        self.form.addRow("Módulo:", self.module)

        self.description = StandardLineEdit(self)
        self.description.setText(description)
        self.description.setAccessibleName("Descripción")
        self.form.addRow("Descripción:", self.description)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(), "module": self.module.text().strip(),
            "description": self.description.text().strip(),
        }


class NewTemplateVersionDialog(FormDialog):
    def __init__(self, parent=None, *, previous_content: str = "") -> None:
        super().__init__(parent, title="Nueva versión")
        self.content = StandardTextArea(self)
        self.content.setPlainText(previous_content)
        self.content.setAccessibleName("Contenido de la nueva versión")
        self.form.addRow("Contenido:", self.content)
        self.add_button_box(ok_text="Crear versión")

    def content_text(self) -> str:
        return self.content.toPlainText().strip()


class RejectTemplateVersionDialog(FormDialog):
    """Rejecting a `DocumentTemplateVersion` always requires a reason —
    the domain (`DocumentTemplateVersion.reject`) rejects a blank one.
    Mirrors `dialogs/feature_flag_dialogs.py::RejectChangeRequestDialog`.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Rechazar versión")
        self.reason = StandardTextArea(self)
        self.reason.setAccessibleName("Motivo de rechazo")
        apply_tooltip(self.reason, "Explica por qué se rechaza esta versión.")
        self.form.addRow("Motivo:", self.reason)
        box = self.add_button_box(ok_text="Rechazar")
        self._ok_button = box.button(QDialogButtonBox.Ok)
        self._ok_button.setEnabled(False)
        self.reason.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self) -> None:
        self._ok_button.setEnabled(bool(self.reason_text()))

    def reason_text(self) -> str:
        return self.reason.toPlainText().strip()
