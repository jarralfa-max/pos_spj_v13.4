"""Edición de cliente (route ``customers.edit``).

Built alongside the module's first real composition root
(``frontend/desktop/modules/customers_crm/composition.py``), wiring the
already-existing backend ``UpdateCustomerUseCase``
(``backend/application/customers/use_cases/lifecycle_use_cases.py``) for
the first time. Field set is deliberately narrower than
``create_customer_page.py``'s: ``UpdateCustomerUseCase`` only supports
``display_name``/``legal_name``/``commercial_name``/``source`` today — no
tax_identifier/phone_e164/email edit path exists yet in this bounded
context, so this page doesn't pretend one does. Shows an empty-state
placeholder until a customer is loaded, same contract
``CustomerProfilePage`` already established for "opened with nothing
selected yet".
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.components import (
    FormField,
    PageHeader,
    StandardForm,
    StandardLineEdit,
    ViewState,
    create_primary_button,
    create_state_widget,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class EditCustomerPage(QWidget):
    customer_updated = pyqtSignal(str)

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("editCustomerPage")
        self._presenter = presenter
        self._customer_id: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)
        root.addWidget(PageHeader(
            self, title="Editar cliente", icon=Icons.CUSTOMERS, compact=True,
            subtitle="Actualiza los datos de identidad de un cliente existente."))

        self._status = QLabel("", self)
        self._status.setObjectName("editCustomerStatus")
        self._status.setWordWrap(True)
        self._status.hide()
        root.addWidget(self._status)

        self._stack = QStackedWidget(self)
        root.addWidget(self._stack, stretch=1)

        self._placeholder = create_state_widget(
            ViewState.EMPTY, self,
            message="Selecciona un cliente desde el Expediente para editarlo.")
        self._stack.addWidget(self._placeholder)

        self._form_page = QWidget(self)
        form_layout = QVBoxLayout(self._form_page)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(Spacing.MD)

        self._form = StandardForm(self._form_page)

        self._display_name = StandardLineEdit(
            self, placeholder="Nombre o razón social", required=True)
        self._form.add_field("display_name", FormField(
            "Nombre para mostrar", self._display_name, required=True))

        self._legal_name = StandardLineEdit(self, placeholder="Razón social")
        self._form.add_field("legal_name", FormField(
            "Razón social", self._legal_name, helper="Opcional"))

        self._commercial_name = StandardLineEdit(self, placeholder="Nombre comercial")
        self._form.add_field("commercial_name", FormField(
            "Nombre comercial", self._commercial_name, helper="Opcional"))

        self._source = StandardLineEdit(self, placeholder="Origen del cliente")
        self._form.add_field("source", FormField(
            "Origen", self._source, helper="Opcional"))

        form_layout.addWidget(self._form)

        self._submit_button = create_primary_button(self, "Guardar cambios")
        self._submit_button.clicked.connect(self._submit)
        form_layout.addWidget(self._submit_button)
        form_layout.addStretch(1)
        self._stack.addWidget(self._form_page)

        self._stack.setCurrentWidget(self._placeholder)

    def ensure_loaded(self) -> None:
        pass  # nothing to show until a customer is selected — see load_customer()

    def reload(self) -> None:
        if self._customer_id is not None:
            self.load_customer(self._customer_id)

    def load_customer(self, customer_id: str) -> None:
        self._customer_id = customer_id
        self._status.hide()
        try:
            view = self._presenter.customer_360(customer_id)
        except Exception as exc:  # a page must always show *something*
            self._status.setProperty("state", "ERROR")
            self._status.setText(f"No fue posible cargar el cliente: {exc}")
            self._status.show()
            self._stack.setCurrentWidget(self._placeholder)
            return
        customer = view.profile.customer
        self._display_name.setText(customer.display_name)
        self._legal_name.setText(customer.legal_name or "")
        self._commercial_name.setText(customer.commercial_name or "")
        self._source.setText(customer.source or "")
        self._form.clear_errors()
        self._stack.setCurrentWidget(self._form_page)

    def _submit(self) -> None:
        if self._customer_id is None:
            return
        errors = self._validate()
        self._form.set_errors(errors)
        if errors:
            self._status.setProperty("state", "ERROR")
            self._status.setText("Revisa los campos marcados antes de continuar.")
            self._status.show()
            return

        result = self._presenter.update_customer(
            self._customer_id,
            display_name=self._display_name.value(),
            legal_name=self._legal_name.value(),
            commercial_name=self._commercial_name.value(),
            source=self._source.value())

        if not result.success:
            self._status.setProperty("state", "ERROR")
            self._status.setText(result.message)
            self._status.show()
            return

        self._status.setProperty("state", "READY")
        self._status.setText(f"Cliente actualizado: {result.message}")
        self._status.show()
        self.customer_updated.emit(self._customer_id)

    def _validate(self) -> dict[str, str]:
        errors: dict[str, str] = {}
        if not self._display_name.is_valid():
            errors["display_name"] = "El nombre es obligatorio."
        return errors
