"""Canonical form-field wrapper."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components.tooltip import Tooltip


class FormField(QWidget):
    """Combines visible label, widget, helper and error text without local styles."""

    def __init__(self, label: str, widget: QWidget, parent=None, *, helper_text: str = "", tooltip: str = "", required: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("formField")
        self.setProperty("component", "formField")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        suffix = " *" if required else ""
        self.label = QLabel(f"{label}{suffix}", self)
        self.widget = widget
        self.helper = QLabel(helper_text, self)
        self.helper.setObjectName("formFieldHelper")
        self.helper.setWordWrap(True)
        self.error = QLabel("", self)
        self.error.setObjectName("formFieldError")
        self.error.setProperty("state", "ERROR")
        layout.addWidget(self.label)
        layout.addWidget(widget)
        if helper_text:
            layout.addWidget(self.helper)
        layout.addWidget(self.error)
        if tooltip:
            Tooltip.attach(widget, title=label, description=tooltip)

    def set_error(self, message: str) -> None:
        self.error.setText(message)
        self.setProperty("state", "ERROR" if message else "DEFAULT")
