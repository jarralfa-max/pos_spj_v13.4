"""Canonical form-field and form layout wrappers."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components.tooltip import Tooltip
from frontend.desktop.themes import DesktopSpacing


class FormField(QWidget):
    """Combines visible label, widget, helper and error text without local styles."""

    def __init__(
        self,
        label: str,
        widget: QWidget,
        parent=None,
        *,
        helper_text: str = "",
        tooltip: str = "",
        required: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formField")
        self.setProperty("component", "formField")
        self.setProperty("state", "DEFAULT")
        self.setProperty("required", required)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(DesktopSpacing.XS)
        suffix = " *" if required else ""
        self.label = QLabel(f"{label}{suffix}", self)
        self.label.setObjectName("formFieldLabel")
        self.widget = widget
        self.helper = QLabel(helper_text, self)
        self.helper.setObjectName("formFieldHelper")
        self.helper.setWordWrap(True)
        self.error = QLabel("", self)
        self.error.setObjectName("formFieldError")
        self.error.setProperty("state", "ERROR")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        layout.addWidget(self.label)
        layout.addWidget(widget)
        if helper_text:
            layout.addWidget(self.helper)
        layout.addWidget(self.error)
        self.set_accessibility(label, helper_text or tooltip)
        if tooltip:
            Tooltip.attach(widget, title=label, description=tooltip)

    def set_accessibility(self, label: str, description: str = "") -> None:
        self.setAccessibleName(label)
        self.widget.setAccessibleName(label)
        if description:
            self.setAccessibleDescription(description)
            self.widget.setAccessibleDescription(description)

    def set_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.setVisible(bool(message))
        self.setProperty("state", "ERROR" if message else "DEFAULT")
        self.widget.setProperty("state", "ERROR" if message else "DEFAULT")
        self.style().unpolish(self)
        self.style().polish(self)
        self.widget.style().unpolish(self.widget)
        self.widget.style().polish(self.widget)

    def clear_error(self) -> None:
        self.set_error("")


class StandardForm(QWidget):
    """Vertical canonical form that owns fields, validation state and focus order."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("standardForm")
        self.setProperty("component", "standardForm")
        self._fields: dict[str, FormField] = {}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(DesktopSpacing.SM)

    def add_field(self, key: str, field: FormField) -> FormField:
        self._fields[key] = field
        self._layout.addWidget(field)
        return field

    def field(self, key: str) -> FormField:
        return self._fields[key]

    def clear_errors(self) -> None:
        for field in self._fields.values():
            field.clear_error()

    def set_error(self, key: str, message: str) -> None:
        self._fields[key].set_error(message)

    def has_errors(self) -> bool:
        return any(field.error.isVisible() for field in self._fields.values())

    def focus_first(self) -> None:
        for field in self._fields.values():
            field.widget.setFocus()
            return

    def focus_first_error(self) -> None:
        for field in self._fields.values():
            if field.error.isVisible():
                field.widget.setFocus()
                return
