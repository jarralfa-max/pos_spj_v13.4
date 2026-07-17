"""FilePathInput (FASE DS-4) — read-only path field + a browse button."""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QWidget

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.themes.tokens import Spacing


class FilePathInput(QWidget):
    path_changed = pyqtSignal(str)

    def __init__(self, parent=None, *, caption: str = "Seleccionar archivo",
                 file_filter: str = "Todos los archivos (*.*)",
                 save_mode: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("filePathInput")
        self._caption = caption
        self._filter = file_filter
        self._save_mode = save_mode

        self._field = QLineEdit(self)
        self._field.setObjectName("filePathField")
        self._field.setReadOnly(True)
        self._field.setProperty("readOnly", True)
        browse = create_secondary_button(self, "Examinar…", tooltip="Elegir archivo")
        browse.clicked.connect(self._browse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(self._field, stretch=1)
        layout.addWidget(browse)

    def path(self) -> str:
        return self._field.text().strip()

    def set_path(self, value: str | None) -> None:
        self._field.setText(value or "")

    def _browse(self) -> None:
        if self._save_mode:
            path, _ = QFileDialog.getSaveFileName(self, self._caption, self.path(), self._filter)
        else:
            path, _ = QFileDialog.getOpenFileName(self, self._caption, self.path(), self._filter)
        if path:
            self.set_path(path)
            self.path_changed.emit(path)
