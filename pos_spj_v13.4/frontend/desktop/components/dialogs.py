"""Canonical enterprise dialogs."""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget


class StandardDialog(QDialog):
    """Dialog shell with standardized title, description, content and buttons."""

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
        layout = QVBoxLayout(self)
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("dialogTitle")
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
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
