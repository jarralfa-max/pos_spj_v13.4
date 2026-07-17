"""BarcodeInput (FASE DS-4) — HID scanner field.

Enter terminates a scan and emits ``scanned(code)`` WITHOUT submitting the host
form (the host connects ``scanned`` explicitly). Exact-match by design; unknown
codes are handled by the host policy (create/lookup), not by this widget.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLineEdit

from frontend.desktop.components.tooltip import apply_tooltip


class BarcodeInput(QLineEdit):
    scanned = pyqtSignal(str)

    def __init__(self, parent=None, *, clear_after_scan: bool = True,
                 placeholder: str = "Escanea o teclea el código") -> None:
        super().__init__(parent)
        self.setObjectName("barcodeInput")
        self.setPlaceholderText(placeholder)
        self._clear_after_scan = clear_after_scan
        apply_tooltip(self, "Lector de código de barras",
                      description="Enter confirma el código sin enviar el formulario.")

    def code(self) -> str:
        return self.text().strip()

    def keyPressEvent(self, event):  # noqa: N802 (Qt override)
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            code = self.code()
            if code:
                self.scanned.emit(code)
                if self._clear_after_scan:
                    self.clear()
            # swallow Enter so it does not trigger the dialog/form default button
            event.accept()
            return
        super().keyPressEvent(event)
