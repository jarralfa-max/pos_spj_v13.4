"""CRM-18 — Alta rápida de cliente (route ``customers.create``).

Every field here is a canonical specialized input (§79) with its own
built-in validation contract (``is_valid()``/``error_message()``) — this
page never reimplements format checks (RFC pattern, email shape, phone
range) that ``TaxIdentifierInput``/``EmailInput``/``PhoneInput`` already
own; it only decides WHEN to show them (on submit) and where
(``FormField.set_error()``). Every text-capable field here also carries the
virtual-keyboard affordance now (§90's "todo input alfanumérico... icono de
teclado") — for ``EmailInput``/``TaxIdentifierInput`` that came for free
once this same phase wired it into the shared component
(``frontend/desktop/components/{email_input,tax_identifier_input}.py``);
``PhoneInput`` still doesn't (see that file's own docstring for why, a
documented gap, not silently missing).
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import (
    EmailInput,
    FormField,
    PageHeader,
    PhoneInput,
    SearchableComboBox,
    StandardForm,
    StandardLineEdit,
    TaxIdentifierInput,
    create_primary_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing

_CUSTOMER_TYPE_OPTIONS = (
    ("INDIVIDUAL", "Persona física"), ("BUSINESS", "Empresa"),
    ("PUBLIC_CUSTOMER", "Público en general"), ("EMPLOYEE", "Empleado"),
    ("INTERNAL", "Interno"), ("OTHER", "Otro"),
)


class CreateCustomerPage(QWidget):
    customer_created = pyqtSignal(str)

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("createCustomerPage")
        self._presenter = presenter

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)
        root.addWidget(PageHeader(
            self, title="Alta rápida", icon=Icons.CUSTOMERS, compact=True,
            subtitle="Registro rápido de un nuevo cliente."))

        self._status = QLabel("", self)
        self._status.setObjectName("createCustomerStatus")
        self._status.setWordWrap(True)
        self._status.hide()
        root.addWidget(self._status)

        self._form = StandardForm(self)

        self._display_name = StandardLineEdit(
            self, placeholder="Nombre o razón social", required=True)
        self._form.add_field("display_name", FormField(
            "Nombre para mostrar", self._display_name, required=True))

        self._customer_type = SearchableComboBox(self, placeholder="Selecciona un tipo")
        self._customer_type.set_options(list(_CUSTOMER_TYPE_OPTIONS))
        self._form.add_field("customer_type", FormField("Tipo de cliente", self._customer_type))

        self._tax_identifier = TaxIdentifierInput(self, kind=TaxIdentifierInput.KIND_RFC)
        self._form.add_field("tax_identifier", FormField(
            "RFC", self._tax_identifier, helper="Opcional"))

        self._phone = PhoneInput(self)
        self._form.add_field("phone_e164", FormField(
            "Teléfono", self._phone, helper="Opcional"))

        self._email = EmailInput(self)
        self._form.add_field("email", FormField("Correo", self._email, helper="Opcional"))

        root.addWidget(self._form)

        self._submit_button = create_primary_button(self, "Crear cliente")
        self._submit_button.clicked.connect(self._submit)
        root.addWidget(self._submit_button)
        root.addStretch(1)

    def ensure_loaded(self) -> None:
        pass  # a blank form needs no data load

    def reload(self) -> None:
        pass

    def _submit(self) -> None:
        errors = self._validate()
        self._form.set_errors(errors)
        if errors:
            self._status.setProperty("state", "ERROR")
            self._status.setText("Revisa los campos marcados antes de continuar.")
            self._status.show()
            return

        result = self._presenter.create_customer(
            display_name=self._display_name.value(),
            customer_type=self._customer_type.current_id() or "INDIVIDUAL",
            tax_identifier=self._tax_identifier.value(),
            phone_e164=self._phone.value() if self._phone.value() else "",
            email=self._email.email())

        if not result.success:
            self._status.setProperty("state", "ERROR")
            self._status.setText(result.message)
            self._status.show()
            return

        self._status.setProperty("state", "READY")
        self._status.setText(f"Cliente creado: {result.message}")
        self._status.show()
        self._reset_form()
        self.customer_created.emit(result.entity_id)

    def _validate(self) -> dict[str, str]:
        errors: dict[str, str] = {}
        if not self._display_name.is_valid():
            errors["display_name"] = "El nombre es obligatorio."
        if self._tax_identifier.value() and not self._tax_identifier.is_valid():
            errors["tax_identifier"] = self._tax_identifier.error_message()
        if self._email.text().strip() and not self._email.is_valid():
            errors["email"] = self._email.error_message()
        if self._phone.value() and not self._phone.is_valid():
            errors["phone_e164"] = "El teléfono debe incluir código de país, p. ej. +5215512345678."
        return errors

    def _reset_form(self) -> None:
        self._display_name.clear()
        self._tax_identifier.clear()
        self._phone.set_value("")
        self._email.clear()
        self._form.clear_errors()
