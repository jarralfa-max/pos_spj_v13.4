"""CRM-N — Customer editing: CustomerCrmPresenter.update_customer(),
EditCustomerPage, and the Expediente <-> Edit round trip. Mirrors
tests/unit/test_customers_crm_create_customer_page.py's shape.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.customers.result import CustomerResult
from frontend.desktop.modules.customers_crm.customers_crm_presenter import CustomerCrmPresenter
from frontend.desktop.modules.customers_crm.customers_crm_workspace import CustomersCrmWorkspace
from frontend.desktop.modules.customers_crm.pages.edit_customer_page import EditCustomerPage
from frontend.desktop.modules.customers_crm.pages.customer_profile_page import CustomerProfilePage
from frontend.desktop.modules.customers_crm.view_models import CustomerCrmCapabilities


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    user_id = "u1"

    def tiene_permiso(self, _permission: str) -> bool:
        return True


class TestCustomerCrmPresenterUpdateCustomer:
    def test_fails_when_unwired(self):
        presenter = CustomerCrmPresenter(session_context=_FakeSession())
        result = presenter.update_customer("c1", display_name="Nuevo nombre")
        assert result.success is False
        assert result.error_code == "NOT_WIRED"

    def test_delegates_to_command_handler_with_actor_and_operation_id(self):
        calls = []

        def _handler(**kwargs):
            calls.append(kwargs)
            return CustomerResult.ok("Cliente actualizado", entity_id="c1")

        presenter = CustomerCrmPresenter(
            session_context=_FakeSession(), command_handlers={"update_customer": _handler})
        result = presenter.update_customer(
            "c1", display_name="Restaurante El Sol", legal_name="El Sol SA de CV")
        assert result.success is True
        assert calls[0]["actor_user_id"] == "u1"
        assert calls[0]["customer_id"] == "c1"
        assert calls[0]["display_name"] == "Restaurante El Sol"
        assert calls[0]["legal_name"] == "El Sol SA de CV"
        assert "operation_id" in calls[0]


def _fake_360_view(*, display_name="Ana Torres", legal_name="", commercial_name="", source=""):
    customer = SimpleNamespace(
        display_name=display_name, legal_name=legal_name,
        commercial_name=commercial_name, source=source)
    profile = SimpleNamespace(customer=customer)
    return SimpleNamespace(profile=profile)


class _FakePresenter:
    def __init__(self, *, view=None, update_result=None) -> None:
        self._view = view or _fake_360_view()
        self._update_result = update_result or CustomerResult.ok(
            "Cliente actualizado", entity_id="c1")
        self.update_calls: list[dict] = []

    def customer_360(self, customer_id: str):
        return self._view

    def update_customer(self, customer_id, **kwargs):
        self.update_calls.append({"customer_id": customer_id, **kwargs})
        return self._update_result


class TestEditCustomerPage:
    def test_starts_on_placeholder_before_a_customer_is_loaded(self, app):
        page = EditCustomerPage(_FakePresenter())
        assert page._stack.currentWidget() is page._placeholder

    def test_load_customer_prefills_form_from_360_view(self, app):
        presenter = _FakePresenter(view=_fake_360_view(
            display_name="Restaurante El Sol", legal_name="El Sol SA de CV",
            commercial_name="El Solecito", source="referido"))
        page = EditCustomerPage(presenter)
        page.load_customer("c1")
        assert page._display_name.value() == "Restaurante El Sol"
        assert page._legal_name.value() == "El Sol SA de CV"
        assert page._commercial_name.value() == "El Solecito"
        assert page._source.value() == "referido"
        assert page._stack.currentWidget() is page._form_page

    def test_empty_display_name_blocks_submit(self, app):
        presenter = _FakePresenter()
        page = EditCustomerPage(presenter)
        page.load_customer("c1")
        page._display_name.clear()
        page._submit()
        assert presenter.update_calls == []
        assert page._form.field("display_name")._error.text()

    def test_valid_submit_calls_presenter_and_emits_signal(self, app):
        presenter = _FakePresenter()
        page = EditCustomerPage(presenter)
        page.load_customer("c1")
        page._display_name.setText("Nuevo nombre")
        received = []
        page.customer_updated.connect(received.append)
        page._submit()
        assert presenter.update_calls[0]["customer_id"] == "c1"
        assert presenter.update_calls[0]["display_name"] == "Nuevo nombre"
        assert received == ["c1"]

    def test_backend_failure_shows_status(self, app):
        presenter = _FakePresenter(
            update_result=CustomerResult.fail("El cliente no existe", "NOT_FOUND"))
        page = EditCustomerPage(presenter)
        page.load_customer("c1")
        page._submit()
        assert page._status.property("state") == "ERROR"
        assert "no existe" in page._status.text().lower()

    def test_reload_after_load_customer_refetches_same_customer(self, app):
        presenter = _FakePresenter()
        page = EditCustomerPage(presenter)
        page.load_customer("c1")
        page.reload()
        assert page._customer_id == "c1"

    def test_load_customer_error_shows_placeholder(self, app):
        class _BrokenPresenter(_FakePresenter):
            def customer_360(self, customer_id):
                raise RuntimeError("boom")

        page = EditCustomerPage(_BrokenPresenter())
        page.load_customer("c1")
        assert page._stack.currentWidget() is page._placeholder
        assert page._status.property("state") == "ERROR"


class TestProfileEditHandoff:
    def test_editar_button_emits_edit_requested(self, app):
        page = CustomerProfilePage(_FakePresenter())
        page._customer_id = "c1"
        received = []
        page.edit_requested.connect(received.append)
        page._request_edit()
        assert received == ["c1"]

    def test_no_signal_when_nothing_selected(self, app):
        page = CustomerProfilePage(_FakePresenter())
        received = []
        page.edit_requested.connect(received.append)
        page._request_edit()
        assert received == []


class TestWorkspaceEditRoundTrip:
    def test_editar_action_navigates_to_edit_then_back_to_profile(self, app):
        capabilities = CustomerCrmCapabilities(module_view=True, clientes=True)

        class _FakePresenterWithCapabilities(_FakePresenter):
            def capabilities(self):
                return capabilities

        workspace = CustomersCrmWorkspace(_FakePresenterWithCapabilities())
        workspace.select_route("customers.profile")
        workspace._profile_page._customer_id = "c1"
        workspace._profile_page._request_edit()

        assert workspace._stack.currentIndex() == workspace._route_index_by_id["customers.edit"]
        assert workspace._edit_page._customer_id == "c1"

        workspace._edit_page._display_name.setText("Nombre actualizado")
        workspace._edit_page._submit()

        assert workspace._stack.currentIndex() == workspace._route_index_by_id["customers.profile"]
