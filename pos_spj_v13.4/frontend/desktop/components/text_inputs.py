"""Standard text inputs for the SPJ desktop Design System."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtWidgets import QAction, QLineEdit, QPlainTextEdit

from frontend.desktop.components.virtual_keyboard import (
    attach_virtual_keyboard_action,
)
from frontend.desktop.themes.tokens import TouchTarget


class StandardLineEdit(QLineEdit):
    """Standard single-line text input.

    Responsibilities:
    - Consistent Design System objectName.
    - Touch-friendly minimum height.
    - Optional required validation.
    - Integrated virtual-keyboard affordance.
    - Accessible metadata.
    - Never owns business/domain logic.

    Use specialized inputs for:
    - money
    - decimal values
    - integers
    - dates
    - phone numbers
    - email addresses
    """

    def __init__(
        self,
        parent=None,
        *,
        placeholder: str = "",
        max_length: Optional[int] = None,
        required: bool = False,
        keyboard_enabled: bool = True,
        keyboard_numeric: bool = False,
        accessible_name: str = "",
    ) -> None:
        super().__init__(parent)

        self.setObjectName("standardLineEdit")
        self.setMinimumHeight(TouchTarget.INPUT_HEIGHT)

        self._required = bool(required)
        self._keyboard_numeric = bool(keyboard_numeric)
        self._virtual_keyboard_action: Optional[QAction] = None

        self.setProperty("required", self._required)
        self.setProperty(
            "inputMode",
            "numeric" if self._keyboard_numeric else "text",
        )

        if placeholder:
            self.setPlaceholderText(placeholder)

        if max_length is not None:
            self.setMaxLength(max(0, int(max_length)))

        if accessible_name:
            self.setAccessibleName(accessible_name)
        elif placeholder:
            self.setAccessibleName(placeholder)

        self.set_keyboard_enabled(keyboard_enabled)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def value(self) -> str:
        """Return the normalized value used by forms."""
        return self.text().strip()

    def is_valid(self) -> bool:
        """Return whether the field satisfies its basic required rule."""
        return bool(self.value()) or not self._required

    def is_required(self) -> bool:
        return self._required

    def set_required(self, required: bool) -> None:
        """Change required state without recreating the widget."""
        required = bool(required)

        if required == self._required:
            return

        self._required = required
        self.setProperty("required", required)

        # Force Qt/QSS to reevaluate dynamic-property selectors.
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def keyboard_enabled(self) -> bool:
        return self._virtual_keyboard_action is not None

    def keyboard_action(self) -> Optional[QAction]:
        """Return the trailing keyboard action, mainly for tests/customization."""
        return self._virtual_keyboard_action

    def set_keyboard_enabled(self, enabled: bool) -> None:
        """Enable/disable the integrated on-screen keyboard action."""
        enabled = bool(enabled)

        if enabled and self._virtual_keyboard_action is None:
            self._virtual_keyboard_action = attach_virtual_keyboard_action(
                self,
                numeric=self._keyboard_numeric,
            )

        elif not enabled and self._virtual_keyboard_action is not None:
            self.removeAction(self._virtual_keyboard_action)
            self._virtual_keyboard_action.deleteLater()
            self._virtual_keyboard_action = None

        self.setProperty("virtualKeyboardEnabled", enabled)

    def focus_and_select_all(self) -> None:
        """Convenience helper for touch/search workflows."""
        self.setFocus()
        self.selectAll()


class StandardTextArea(QPlainTextEdit):
    """Standard multiline free-text input."""

    def __init__(
        self,
        parent=None,
        *,
        placeholder: str = "",
        max_length: Optional[int] = None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("standardTextArea")
        self._max_length = max_length

        if placeholder:
            self.setPlaceholderText(placeholder)

        if max_length is not None:
            self.textChanged.connect(self._enforce_max_length)

    def value(self) -> str:
        return self.toPlainText().strip()

    def _enforce_max_length(self) -> None:
        if self._max_length is None:
            return

        text = self.toPlainText()

        if len(text) <= self._max_length:
            return

        cursor = self.textCursor()
        position = cursor.position()

        self.blockSignals(True)
        self.setPlainText(text[: self._max_length])
        self.blockSignals(False)

        cursor.setPosition(min(position, self._max_length))
        self.setTextCursor(cursor)


class PasswordInput(QLineEdit):
    """Masked password input.

    The virtual keyboard is intentionally not attached automatically here.
    Authentication screens can opt into a secure keyboard implementation
    separately.
    """

    def __init__(
        self,
        parent=None,
        *,
        placeholder: str = "Contraseña",
    ) -> None:
        super().__init__(parent)

        self.setObjectName("passwordInput")
        self.setMinimumHeight(TouchTarget.INPUT_HEIGHT)
        self.setEchoMode(QLineEdit.Password)
        self.setPlaceholderText(placeholder)
        self.setAccessibleName("Contraseña")

    def set_revealed(self, revealed: bool) -> None:
        self.setEchoMode(
            QLineEdit.Normal if revealed else QLineEdit.Password
        )

    def value(self) -> str:
        return self.text()