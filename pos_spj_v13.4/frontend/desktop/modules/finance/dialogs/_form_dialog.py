"""Base form dialog for the finance module (StandardDialog policy).

Auditoría d9f2bca F25: «Aceptar» con datos inválidos ya no se traga el clic en
silencio. El diálogo queda abierto, conserva lo escrito y muestra la causa en
una línea de error dentro del formulario. Cada diálogo declara su causa en
``_validation_error()``; los que sólo implementan ``_is_valid()`` reciben un
mensaje genérico.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components.dialogs import FormDialog


class FinanceFormDialog(FormDialog):
    dialog_title = ""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title=self.dialog_title)
        self._build_form()
        self.error_label = QLabel("", self)
        self.error_label.setObjectName("formErrorLabel")
        self.error_label.setProperty("role", "error")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.form.addRow(self.error_label)
        self.add_button_box(on_accept=self._accept_if_valid)

    def _build_form(self) -> None:
        raise NotImplementedError

    def _is_valid(self) -> bool:
        return True

    def _validation_error(self) -> str | None:
        """Causa del rechazo, o ``None`` si la captura es válida."""
        return None if self._is_valid() else "Revise los campos obligatorios del formulario."

    def _accept_if_valid(self) -> None:
        error = self._validation_error()
        if error:
            self.error_label.setText(error)
            self.error_label.show()
            return
        self.error_label.hide()
        self.accept()
