"""CRM-18 — Formularios: virtual-keyboard wiring on shared inputs,
``CustomerCrmPresenter.create_customer()``, ``CreateCustomerPage``
validation, and the create-to-Expediente handoff.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.customers.result import CustomerResult
from frontend.desktop.components.address_input import AddressInput
from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.email_input import EmailInput
from frontend.desktop.components.integer_input import IntegerInput
from frontend.desktop.components.tax_identifier_input import TaxIdentifierInput
from frontend.desktop.modules.customers_crm.customers_crm_presenter import CustomerCrmPresenter
from frontend.desktop.modules.customers_crm.customers_crm_workspace import CustomersCrmWorkspace
from frontend.desktop.modules.customers_crm.pages.create_customer_page import CreateCustomerPage
from frontend.desktop.modules.customers_crm.view_models import CustomerCrmCapabilities


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    user_id = "u1"

    def tiene_permiso(self, _permission: str) -> bool:
        return True


class TestVirtualKeyboardWiring:
    """§90: "todo input alfanumérico... icono de teclado" — every
    specialized QLineEdit-backed input this phase touched must carry the
    trailing keyboard action (the ``virtualKeyboard`` dynamic property
    ``attach_virtual_keyboard_action`` sets)."""

    def test_email_input_has_keyboard_action(self, app):
        assert EmailInput().property("virtualKeyboard") == "text"

    def test_tax_identifier_input_has_keyboard_action(self, app):
        assert TaxIdentifierInput().property("virtualKeyboard") == "text"

    def test_decimal_input_has_numeric_keyboard_action(self, app):
        assert DecimalInput().property("virtualKeyboard") == "numeric"

    def test_integer_input_line_edit_has_numeric_keyboard_action(self, app):
        assert IntegerInput().lineEdit().property("virtualKeyboard") == "numeric"

    def test_address_input_search_box_has_keyboard_action(self, app):
        widget = AddressInput()
        assert widget._search_box.property("virtualKeyboard") == "text"


class TestCustomerCrmPresenterCreateCustomer:
    def test_fails_when_unwired(self):
        presenter = CustomerCrmPresenter(session_context=_FakeSession())
        result = presenter.create_customer(display_name="Cliente", customer_type="INDIVIDUAL")
        assert result.success is False
        assert result.error_code == "NOT_WIRED"

    def test_delegates_to_command_handler_with_actor_and_operation_id(self):
        calls = []

        def _handler(**kwargs):
            calls.append(kwargs)
            return CustomerResult.ok("Cliente creado", entity_id="c1")

        presenter = CustomerCrmPresenter(
            session_context=_FakeSession(), command_handlers={"create_customer": _handler})
        result = presenter.create_customer(
            display_name="Restaurante El Sol", customer_type="BUSINESS",
            tax_identifier="", phone_e164="", email="")
        assert result.success is True
        assert result.entity_id == "c1"
        assert calls[0]["actor_user_id"] == "u1"
        assert calls[0]["display_name"] == "Restaurante El Sol"
        assert calls[0]["customer_type"] == "BUSINESS"
        assert calls[0]["tax_identifier"] is None  # empty string normalized to None
        assert "operation_id" in calls[0]


class _FakePresenter:
    def __init__(self, result=None) -> None:
        self._result = result or CustomerResult.ok("Cliente creado", entity_id="c1")
        self.calls: list[dict] = []

    def create_customer(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


class TestCreateCustomerPage:
    def test_empty_display_name_blocks_submit(self, app):
        presenter = _FakePresenter()
        page = CreateCustomerPage(presenter)
        page._submit()
        assert presenter.calls == []
        assert page._form.field("display_name")._error.text()

    def test_valid_submit_calls_presenter_and_clears_form(self, app):
        presenter = _FakePresenter()
        page = CreateCustomerPage(presenter)
        page._display_name.setText("Restaurante El Sol")
        received = []
        page.customer_created.connect(received.append)
        page._submit()
        assert presenter.calls[0]["display_name"] == "Restaurante El Sol"
        assert received == ["c1"]
        assert page._display_name.text() == ""

    def test_invalid_rfc_blocks_submit(self, app):
        presenter = _FakePresenter()
        page = CreateCustomerPage(presenter)
        page._display_name.setText("Restaurante El Sol")
        page._tax_identifier.setText("NO-VALIDO")
        page._submit()
        assert presenter.calls == []
        assert page._form.field("tax_identifier")._error.text()

    def test_invalid_email_blocks_submit(self, app):
        presenter = _FakePresenter()
        page = CreateCustomerPage(presenter)
        page._display_name.setText("Restaurante El Sol")
        page._email.setText("not-an-email")
        page._submit()
        assert presenter.calls == []
        assert page._form.field("email")._error.text()

    def test_backend_failure_shows_status_without_clearing_form(self, app):
        presenter = _FakePresenter(CustomerResult.fail("Cliente duplicado", "DUPLICATE"))
        page = CreateCustomerPage(presenter)
        page._display_name.setText("Restaurante El Sol")
        page._submit()
        assert page._status.property("state") == "ERROR"
        assert "duplicado" in page._status.text().lower()
        assert page._display_name.text() == "Restaurante El Sol"  # not cleared on failure

    def test_default_customer_type_is_individual(self, app):
        presenter = _FakePresenter()
        page = CreateCustomerPage(presenter)
        page._display_name.setText("Juan Perez")
        page._submit()
        assert presenter.calls[0]["customer_type"] == "INDIVIDUAL"


class TestCreateCustomerToExpedienteHandoff:
    def test_successful_create_navigates_to_new_customers_profile(self, app):
        capabilities = CustomerCrmCapabilities(module_view=True, clientes=True)

        class _FakePresenterWithCapabilities(_FakePresenter):
            def capabilities(self):
                return capabilities

        workspace = CustomersCrmWorkspace(_FakePresenterWithCapabilities())
        workspace.select_route("customers.create")
        page = workspace._stack.currentWidget().findChild(CreateCustomerPage)
        page._display_name.setText("Cliente nuevo")
        page._submit()

        assert workspace._stack.currentIndex() == workspace._route_index_by_id["customers.profile"]
        assert workspace._profile_page._customer_id == "c1"
