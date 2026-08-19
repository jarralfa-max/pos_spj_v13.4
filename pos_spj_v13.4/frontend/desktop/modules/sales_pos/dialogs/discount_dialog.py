"""DiscountDialog (POS-19) — real counterpart to SALES-8's
`ApplySaleDiscountUseCase` (§62 hot authorization: a large discount needs a
distinct authorizer holding `DISCOUNT_OVERRIDE`, already enforced inside
the use case — this dialog only collects the fields, never re-implements
the threshold check the domain policy owns).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import QDialog, QVBoxLayout

from frontend.desktop.components import FormField, MoneyInput, StandardForm, StandardLineEdit, create_primary_button


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
        self._authorizer = StandardLineEdit(self, placeholder="ID de autorizador (si aplica)")
        form.add_field("authorizer_user_id", FormField(
            "Autorizador", self._authorizer, helper="Requerido solo para descuentos grandes"))
        self._reason = StandardLineEdit(self, placeholder="Motivo")
        form.add_field("reason", FormField("Motivo", self._reason))
        root.addWidget(form)

        submit = create_primary_button(self, "Aplicar")
        submit.clicked.connect(self._submit)
        root.addWidget(submit)

        self._status = None

    def _submit(self) -> None:
        try:
            amount = Decimal(str(self._amount.value() or "0"))
        except (InvalidOperation, TypeError):
            return
        result = self._presenter.apply_sale_discount(
            sale_id=self._sale_id, discount_amount=amount,
            authorizer_user_id=self._authorizer.value() or None,
            reason=self._reason.value() or None)
        if result.success:
            self.applied = True
            self.accept()
