"""CouponsVouchersPage (LOY-25, routes ``instruments.coupons``/
``instruments.vouchers``) — issue a coupon or voucher instance for a
customer, given an already-configured definition id.

No definitions directory is built yet (creating `CouponDefinition`/
`VoucherDefinition` rows still requires a direct repository call or a
future admin page) — this page only covers ISSUING an instance against a
definition id an operator already has on hand, same "start with the
highest-value single action, not the whole CRUD surface" scoping every
earlier LOY-N phase's own use-case work already applied.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import FormField, StandardForm
from frontend.desktop.components.buttons import create_primary_button
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.tokens import Spacing


class CouponsVouchersPage(QWidget):
    def __init__(self, presenter, parent=None, *, mode: str) -> None:
        super().__init__(parent)
        self._mode = mode  # "coupon" | "voucher"
        self.setObjectName(f"fidelidad{mode.capitalize()}sPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        title = "Emitir cupón" if mode == "coupon" else "Emitir vale"
        layout.addWidget(QLabel(title, self))

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        self._form = StandardForm(self)
        self._definition_id_input = StandardLineEdit(self)
        self._form.add_field(
            "definition_id", FormField("ID de la definición", self._definition_id_input,
                                       required=True))
        self._customer_id_input = StandardLineEdit(self)
        self._form.add_field(
            "customer_id", FormField("ID de cliente", self._customer_id_input, required=True))
        self._amount_input: StandardLineEdit | None = None
        if mode == "voucher":
            self._amount_input = StandardLineEdit(self)
            self._form.add_field(
                "amount", FormField("Monto del vale", self._amount_input, required=True))
        layout.addWidget(self._form)

        issue_btn = create_primary_button(
            self, "Emitir cupón" if mode == "coupon" else "Emitir vale")
        issue_btn.clicked.connect(self._issue)
        layout.addWidget(issue_btn)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        pass

    def _issue(self) -> None:
        errors = {}
        definition_id = self._definition_id_input.text().strip()
        customer_id = self._customer_id_input.text().strip()
        if not definition_id:
            errors["definition_id"] = "Obligatorio"
        if not customer_id:
            errors["customer_id"] = "Obligatorio"
        amount: Decimal | None = None
        if self._amount_input is not None:
            try:
                amount = Decimal(self._amount_input.text().strip())
                if amount <= 0:
                    errors["amount"] = "Debe ser positivo"
            except (InvalidOperation, ValueError):
                errors["amount"] = "Monto inválido"
        self._form.set_errors(errors)
        if errors:
            return

        if self._mode == "coupon":
            result = self._presenter.issue_coupon(
                definition_id=definition_id, customer_id=customer_id)
        else:
            result = self._presenter.issue_voucher(
                definition_id=definition_id, customer_id=customer_id, amount=amount)

        if result.success:
            code = result.data.get("instance")
            code_text = getattr(code, "code", "") if code is not None else ""
            self._show_message(f"{result.message} ({code_text})".strip(), error=False)
            self._definition_id_input.clear()
            self._customer_id_input.clear()
            if self._amount_input is not None:
                self._amount_input.clear()
            self._form.clear_errors()
        else:
            self._show_message(result.message, error=True)

    def _show_message(self, message: str, *, error: bool) -> None:
        self._status.setProperty("state", "ERROR" if error else "READY")
        self._status.setText(message)
        self._status.show()
