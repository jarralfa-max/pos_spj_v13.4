"""Base form dialog for the HR module (StandardDialog policy).

No inline colors, standard button box, uniform margins. Subclasses build the
form and expose ``values()`` for the page to forward to the presenter.

Auditoría RRHH cebf67a HR-20: el diálogo se cerraba ANTES de ejecutar el
backend y una falla tiraba la captura. Con ``on_submit`` la operación corre
desde el botón Aceptar: si el backend rechaza, el diálogo sigue abierto con lo
capturado y muestra el motivo junto al formulario.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components.dialogs import FormDialog


class HRFormDialog(FormDialog):
    dialog_title = ""

    def __init__(self, parent=None, *, on_submit=None) -> None:
        super().__init__(parent, title=self.dialog_title)
        self._on_submit = on_submit
        self._build_form()
        self._error_label = QLabel("", self)
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        self.form.addRow(self._error_label)
        self.add_button_box(on_accept=self._accept_if_valid)

    def _build_form(self) -> None:
        raise NotImplementedError

    def _error(self) -> str | None:
        """Return a validation message, or None when the form is valid."""
        return None

    def values(self) -> dict:
        raise NotImplementedError

    def show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(bool(message))

    def _accept_if_valid(self) -> None:
        from frontend.desktop.components.dialogs import MessageDialog
        error = self._error()
        if error:
            if self._on_submit is None:
                MessageDialog.warning(self, self.dialog_title, error)
            else:
                self.show_error(error)
            return
        if self._on_submit is not None:
            ok, message = self._on_submit(self.values())
            if not ok:
                self.show_error(message)
                return
            self.submitted_message = message
        self.accept()
