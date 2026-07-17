"""Basic text fields (FASE DS-4): StandardLineEdit, StandardTextArea, PasswordInput."""

from __future__ import annotations

from PyQt5.QtWidgets import QLineEdit, QPlainTextEdit


class StandardLineEdit(QLineEdit):
    """Short free text. Use specialized inputs for phone/email/money/etc."""

    def __init__(self, parent=None, *, placeholder: str = "", max_length: int | None = None,
                 required: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("standardLineEdit")
        self._required = required
        if placeholder:
            self.setPlaceholderText(placeholder)
        if max_length:
            self.setMaxLength(max_length)

    def value(self) -> str:
        return self.text().strip()

    def is_valid(self) -> bool:
        return bool(self.value()) or not self._required


class StandardTextArea(QPlainTextEdit):
    """Long free text."""

    def __init__(self, parent=None, *, placeholder: str = "", max_length: int | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("standardTextArea")
        self._max_length = max_length
        if placeholder:
            self.setPlaceholderText(placeholder)
        if max_length:
            self.textChanged.connect(self._enforce_max_length)

    def value(self) -> str:
        return self.toPlainText().strip()

    def _enforce_max_length(self) -> None:
        text = self.toPlainText()
        if self._max_length and len(text) > self._max_length:
            cursor = self.textCursor()
            pos = cursor.position()
            self.blockSignals(True)
            self.setPlainText(text[: self._max_length])
            self.blockSignals(False)
            cursor.setPosition(min(pos, self._max_length))
            self.setTextCursor(cursor)


class PasswordInput(QLineEdit):
    """Masked field with an optional reveal toggle."""

    def __init__(self, parent=None, *, placeholder: str = "Contraseña") -> None:
        super().__init__(parent)
        self.setObjectName("passwordInput")
        self.setEchoMode(QLineEdit.Password)
        self.setPlaceholderText(placeholder)

    def set_revealed(self, revealed: bool) -> None:
        self.setEchoMode(QLineEdit.Normal if revealed else QLineEdit.Password)

    def value(self) -> str:
        return self.text()
