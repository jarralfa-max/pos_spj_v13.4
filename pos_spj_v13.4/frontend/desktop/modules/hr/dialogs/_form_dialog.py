"""Base form dialog for the HR module (StandardDialog policy).

No inline colors, standard button box, uniform margins. Subclasses build the
form and expose ``values()`` for the page to forward to the presenter.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout


class HRFormDialog(QDialog):
    dialog_title = ""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("standardDialog")
        self.setWindowTitle(self.dialog_title)
        self.setMinimumWidth(440)
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

    def _error(self) -> str | None:
        """Return a validation message, or None when the form is valid."""
        return None

    def values(self) -> dict:
        raise NotImplementedError

    def _accept_if_valid(self) -> None:
        from PyQt5.QtWidgets import QMessageBox
        error = self._error()
        if error:
            QMessageBox.warning(self, self.dialog_title, error)
            return
        self.accept()
