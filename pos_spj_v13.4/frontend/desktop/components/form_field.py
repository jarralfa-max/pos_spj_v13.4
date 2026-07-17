"""FormField + StandardForm (FASE DS-4/§28).

A FormField wraps a label + input + helper text + tooltip + error text with a
consistent visual state. StandardForm stacks fields inside a SectionCard-like
layout. Placeholder is never a substitute for a label; required fields carry a
visual + accessible marker.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.themes.tokens import Spacing


class FieldState:
    DEFAULT = "default"
    FOCUSED = "focused"
    VALID = "valid"
    WARNING = "warning"
    ERROR = "error"
    DISABLED = "disabled"
    READ_ONLY = "read_only"
    LOADING = "loading"


class FormField(QWidget):
    def __init__(self, label: str, field: QWidget, parent=None, *,
                 required: bool = False, helper: str | None = None,
                 tooltip: str | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("formField")
        self._field = field

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.XXS)

        label_text = f"{label} *" if required else label
        self._label = QLabel(label_text, self)
        self._label.setObjectName("formFieldLabel")
        self._label.setBuddy(field)
        if required:
            self._label.setAccessibleDescription("Campo obligatorio")
        layout.addWidget(self._label)
        layout.addWidget(field)

        self._helper = QLabel(helper or "", self)
        self._helper.setObjectName("formFieldHelper")
        self._helper.setProperty("role", "muted")
        self._helper.setWordWrap(True)
        self._helper.setVisible(bool(helper))
        layout.addWidget(self._helper)

        self._error = QLabel("", self)
        self._error.setObjectName("formFieldError")
        self._error.setProperty("state", "error")
        self._error.setWordWrap(True)
        self._error.setVisible(False)
        layout.addWidget(self._error)

        if tooltip:
            apply_tooltip(field, tooltip)
        field.setAccessibleName(label)

    def field(self) -> QWidget:
        return self._field

    def set_error(self, message: str | None) -> None:
        """Show/clear an inline error. Empty/None clears the error state."""
        has_error = bool(message)
        self._error.setText(message or "")
        self._error.setVisible(has_error)
        self._field.setProperty("state", FieldState.ERROR if has_error else FieldState.DEFAULT)
        style = self._field.style()
        if style is not None:
            style.unpolish(self._field)
            style.polish(self._field)


class StandardForm(QWidget):
    """Vertical stack of FormFields with consistent spacing."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("standardForm")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(Spacing.MD)
        self._fields: dict[str, FormField] = {}

    def add_field(self, key: str, form_field: FormField) -> FormField:
        self._fields[key] = form_field
        self._layout.addWidget(form_field)
        return form_field

    def field(self, key: str) -> FormField | None:
        return self._fields.get(key)

    def set_errors(self, errors: dict[str, str]) -> None:
        for key, form_field in self._fields.items():
            form_field.set_error(errors.get(key))

    def clear_errors(self) -> None:
        for form_field in self._fields.values():
            form_field.set_error(None)
