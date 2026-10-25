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
    """También autoriza un beneficio sobre el margen protegido (auditoría
    Fidelidad 968e0bc FID-03): mismo usuario + clave + motivo."""

    def __init__(self, presenter, *, message: str, parent=None,
                 title: str = "Autorizar venta sin existencia",
                 ok_text: str = "Autorizar y cobrar",
                 reason_prompt: str = "Captura el motivo de la venta sin existencia.") -> None:
        super().__init__(parent, title=title)
        self._reason_prompt = reason_prompt
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

        box = self.add_button_box(ok_text=ok_text)
        box.accepted.disconnect()
        box.accepted.connect(self._authorize)

    def _error(self, message: str) -> None:
        self._status.setProperty("state", "ERROR")
        self._status.setText(message)
        self._status.show()

    def _authorize(self) -> None:
        motivo = self._reason.value().strip()
        if not motivo:
            self._error(self._reason_prompt)
            return
        user_id, problema = self._presenter.verify_authorizer(
            self._user.value().strip(), self._password.value())
        if user_id is None:
            self._error(problema)
            return
        self.authorizer_user_id, self.reason = user_id, motivo
        self.accept()


def ask_margin_authorization(presenter, message: str, parent, ok_text: str):
    """(autorizador, motivo) si otra persona autoriza el beneficio sobre el
    margen protegido; (None, None) si se cancela (FID-03)."""
    from frontend.desktop.modules.sales_pos.dialogs.stock_authorization_dialog import (
        StockAuthorizationDialog,
    )
    dialogo = StockAuthorizationDialog(
        presenter, message=message, parent=parent, title="Autorizar beneficio sobre el margen",
        ok_text=ok_text, reason_prompt="Captura el motivo del beneficio sobre el margen.")
    if dialogo.exec_() and dialogo.authorizer_user_id:
        return dialogo.authorizer_user_id, dialogo.reason
    return None, None
