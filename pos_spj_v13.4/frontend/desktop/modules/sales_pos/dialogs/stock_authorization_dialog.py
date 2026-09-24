"""StockAuthorizationDialog (Fase 6, 2026-09-18) — autorizar una venta sin
existencia suficiente.

Decisión del usuario: si la existencia (directa + reconstruible) no alcanza, se
cobra sólo si OTRO usuario con `POS.venta.sin_existencia` autoriza con su
usuario y clave, más un motivo; el inventario queda negativo y auditado. Este
diálogo sólo captura: la clave la verifica el presentador
(`VerifyAuthorizerCredentialsUseCase`) y el permiso lo revalida el caso de uso.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components import FormDialog, PasswordInput, StandardLineEdit


class StockAuthorizationDialog(FormDialog):
    def __init__(self, presenter, *, message: str, parent=None) -> None:
        super().__init__(parent, title="Autorizar venta sin existencia")
        self.setObjectName("posStockAuthorizationDialog")
        self._presenter = presenter
        self.authorizer_user_id: str | None = None
        self.reason: str | None = None

        aviso = QLabel(message, self)
        aviso.setWordWrap(True)
        self.form.addRow(aviso)
        self._user = StandardLineEdit(self, placeholder="Usuario de quien autoriza")
        self._password = PasswordInput(self, placeholder="Clave de quien autoriza")
        self._reason = StandardLineEdit(self, placeholder="Motivo (obligatorio)")
        self.form.addRow("Autoriza", self._user)
        self.form.addRow("Clave", self._password)
        self.form.addRow("Motivo", self._reason)
        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.hide()
        self.form.addRow(self._status)

        box = self.add_button_box(ok_text="Autorizar y cobrar")
        box.accepted.disconnect()
        box.accepted.connect(self._authorize)

    def _error(self, message: str) -> None:
        self._status.setProperty("state", "ERROR")
        self._status.setText(message)
        self._status.show()

    def _authorize(self) -> None:
        motivo = self._reason.value().strip()
        if not motivo:
            self._error("Captura el motivo de la venta sin existencia.")
            return
        user_id, problema = self._presenter.verify_authorizer(
            self._user.value().strip(), self._password.value())
        if user_id is None:
            self._error(problema)
            return
        self.authorizer_user_id, self.reason = user_id, motivo
        self.accept()
