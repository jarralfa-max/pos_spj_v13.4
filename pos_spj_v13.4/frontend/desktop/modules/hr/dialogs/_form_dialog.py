"""Base form dialog for the HR module (StandardDialog policy).

No inline colors, standard button box, uniform margins. Subclasses build the
form and expose ``values()`` for the page to forward to the presenter.
"""

from __future__ import annotations

from frontend.desktop.components.dialogs import FormDialog


class HRFormDialog(FormDialog):
    dialog_title = ""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title=self.dialog_title)
        self._build_form()
        self.add_button_box(on_accept=self._accept_if_valid)

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
