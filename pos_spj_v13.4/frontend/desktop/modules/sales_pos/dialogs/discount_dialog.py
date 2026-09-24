"""DiscountDialog (POS-19) — real counterpart to SALES-8's
`ApplySaleDiscountUseCase` (§62 hot authorization: a large discount needs a
distinct authorizer holding `DISCOUNT_OVERRIDE`, already enforced inside
the use case — this dialog only collects the fields, never re-implements
the threshold check the domain policy owns).

Fase 5 (2026-09-18): el autorizador se identificaba tecleando su UUID —sin
clave—, y un fallo cerraba nada y no decía nada. Ahora se captura usuario y
clave, el presentador los verifica con el mismo estándar que el login
(`VerifyAuthorizerCredentialsUseCase`) y el motivo del rechazo se muestra: bajo
el precio mínimo o sobre el umbral, el caso de uso dice qué falta.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import QDialog, QLabel, QVBoxLayout

from frontend.desktop.components import (
    FormField,
    MoneyInput,
    PasswordInput,
    StandardForm,
    StandardLineEdit,
    create_primary_button,
)


class DiscountDialog(QDialog):
    def __init__(self, presenter, *, sale_id: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posDiscountDialog")
        self.setWindowTitle("Aplicar descuento")
        self._presenter = presenter
        self._sale_id = sale_id
        self.applied = False

        root = QVBoxLayout(self)
        form = StandardForm(self)
        self._amount = MoneyInput(self)
        form.add_field("discount_amount", FormField("Monto de descuento", self._amount, required=True))
        self._authorizer = StandardLineEdit(self, placeholder="Usuario de quien autoriza")
        form.add_field("authorizer", FormField(
            "Autoriza", self._authorizer,
            helper="Sólo si el descuento es grande o deja el precio bajo el mínimo"))
        self._password = PasswordInput(self, placeholder="Clave de quien autoriza")
        form.add_field("authorizer_password", FormField("Clave", self._password))
        self._reason = StandardLineEdit(self, placeholder="Motivo")
        form.add_field("reason", FormField("Motivo", self._reason))
        root.addWidget(form)

        self._status = QLabel("", self)
        self._status.setObjectName("posDiscountStatus")
        self._status.setWordWrap(True)
        self._status.hide()
        root.addWidget(self._status)

        submit = create_primary_button(self, "Aplicar")
        submit.clicked.connect(self._submit)
        root.addWidget(submit)

    def _show_error(self, message: str) -> None:
        self._status.setProperty("state", "ERROR")
        self._status.setText(message)
        self._status.show()

    def _submit(self) -> None:
        try:
            # `decimal_value()`: el `value()` del spinbox es float.
            amount = Decimal(str(self._amount.decimal_value() or "0"))
        except (InvalidOperation, TypeError):
            self._show_error("Captura un monto de descuento válido.")
            return
        if amount <= 0:
            self._show_error("Captura un monto de descuento mayor a cero.")
            return

        authorizer_user_id = None
        usuario = self._authorizer.value().strip()
        if usuario:
            authorizer_user_id, motivo = self._presenter.verify_authorizer(
                usuario, self._password.value())
            if authorizer_user_id is None:
                self._show_error(motivo)
                return

        result = self._presenter.apply_sale_discount(
            sale_id=self._sale_id, discount_amount=amount,
            authorizer_user_id=authorizer_user_id,
            reason=self._reason.value().strip() or None)
        if result.success:
            self.applied = True
            self.accept()
            return
        self._show_error(result.message)
