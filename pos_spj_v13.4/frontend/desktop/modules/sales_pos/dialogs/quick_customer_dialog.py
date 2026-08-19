"""QuickCustomerDialog (POS-19) — real counterpart to SALES-10's
`QuickCreateCustomerForSaleUseCase`. Same field set the use case itself
supports (display name + optional phone) — never a wider form than the
domain action actually accepts.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QVBoxLayout

from frontend.desktop.components import FormField, PhoneInput, StandardForm, StandardLineEdit, create_primary_button


class QuickCustomerDialog(QDialog):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posQuickCustomerDialog")
        self.setWindowTitle("Cliente rápido")
        self._presenter = presenter
        self.customer_id: str | None = None

        root = QVBoxLayout(self)
        form = StandardForm(self)
        self._name = StandardLineEdit(self, placeholder="Nombre del cliente", required=True)
        form.add_field("display_name", FormField("Nombre", self._name, required=True))
        self._phone = PhoneInput(self)
        form.add_field("phone_e164", FormField("Teléfono", self._phone, helper="Opcional"))
        root.addWidget(form)

        submit = create_primary_button(self, "Crear cliente")
        submit.clicked.connect(self._submit)
        root.addWidget(submit)

    def _submit(self) -> None:
        if not self._name.is_valid():
            return
        result = self._presenter.quick_create_customer(
            display_name=self._name.value(),
            phone_e164=self._phone.value() if self._phone.value() else None)
        if result.success:
            self.customer_id = result.entity_id
            self.accept()
