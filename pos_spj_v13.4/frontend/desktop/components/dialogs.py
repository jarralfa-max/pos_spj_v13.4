"""Canonical enterprise dialogs."""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget


class StandardDialog(QDialog):
    """Dialog shell with standardized title, description, content, focus and buttons."""

    BUTTON_TEXTS = {
        QDialogButtonBox.Ok: "Aceptar",
        QDialogButtonBox.Save: "Guardar",
        QDialogButtonBox.Cancel: "Cancelar",
        QDialogButtonBox.Close: "Cerrar",
        QDialogButtonBox.Yes: "Confirmar",
        QDialogButtonBox.No: "Cancelar",
        QDialogButtonBox.Discard: "Eliminar",
    }

    def __init__(
        self,
        parent=None,
        *,
        title: str,
        description: str = "",
        content: QWidget | None = None,
        buttons: QDialogButtonBox.StandardButtons = QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("standardDialog")
        self.setProperty("component", "standardDialog")
        self.setWindowTitle(title)
        self.setModal(True)
        layout = QVBoxLayout(self)
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("dialogTitle")
        self.title_label.setAccessibleName(title)
        layout.addWidget(self.title_label)
        self.description_label = QLabel(description, self)
        self.description_label.setObjectName("dialogDescription")
        self.description_label.setWordWrap(True)
        if description:
            layout.addWidget(self.description_label)
        self.content = content
        if content is not None:
            layout.addWidget(content, 1)
        self.button_box = QDialogButtonBox(buttons, self)
        self._localize_buttons()
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _localize_buttons(self) -> None:
        for standard_button, text in self.BUTTON_TEXTS.items():
            button = self.button_box.button(standard_button)
            if button is not None:
                button.setText(text)
                button.setAccessibleName(text)

    def set_initial_focus(self, widget: QWidget | None) -> None:
        if widget is not None:
            widget.setFocus()
