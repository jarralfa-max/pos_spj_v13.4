"""Base form dialog for the finance module (StandardDialog policy)."""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout


class FinanceFormDialog(QDialog):
    dialog_title = ""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("standardDialog")
        self.setWindowTitle(self.dialog_title)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.form = QFormLayout()
        self.form.setSpacing(10)
        layout.addLayout(self.form)
        self._build_form()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("Aceptar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_form(self) -> None:
        raise NotImplementedError

    def _is_valid(self) -> bool:
        return True

    def _accept_if_valid(self) -> None:
        if self._is_valid():
            self.accept()
