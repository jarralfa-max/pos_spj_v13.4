"""CRM-17 — Expedientes: PillTabBar, CustomerProfilePage, presenter
``customer_360()``, and directory-to-profile navigation."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from frontend.desktop.modules.customers_crm.customers_crm_presenter import CustomerCrmPresenter
from frontend.desktop.modules.customers_crm.customers_crm_workspace import CustomersCrmWorkspace
from frontend.desktop.modules.customers_crm.pages._pill_tab_bar import PillTabBar
from frontend.desktop.modules.customers_crm.pages.customer_profile_page import (
    CustomerProfilePage,
)
from frontend.desktop.modules.customers_crm.view_models import CustomerCrmCapabilities


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    user_id = "u1"

    def tiene_permiso(self, _permission: str) -> bool:
        return True


class _FakeCode:
    def __str__(self) -> str:
        return "C-0001"


def _customer_360_view():
    customer = SimpleNamespace(
        display_name="Restaurante El Sol", code=_FakeCode(),
        legal_name="El Sol SA de CV", commercial_name="El Sol",
        customer_type=SimpleNamespace(value="BUSINESS"),
        status=SimpleNamespace(value="ACTIVE"),
        lifecycle_stage=SimpleNamespace(value="CUSTOMER"),
        account_owner_user_id="u-vendedor")
    profile = SimpleNamespace(
        customer=customer, contacts=[], addresses=[],
        tax_profile=SimpleNamespace(tax_identifier="XAXX010101000"))
    return SimpleNamespace(
        profile=profile, credit_summary=SimpleNamespace(
            status="AUTHORIZED", credit_limit="10000.00", available_credit="8000.00",
            current_exposure="2000.00", overdue_amount="0.00", receivable_status="AL_CORRIENTE"),
        active_consents=[], ownership_by_type={}, current_portfolio=None,
        active_segments=[SimpleNamespace()], active_tags=[],
        open_opportunities=[], open_cases=[], recent_activities=[], pending_tasks=[],
        open_duplicate_candidates=[], open_quality_issues=[], recent_history=[],
        orders_summary=SimpleNamespace(total_orders=3, open_orders=1),
        delivery_summary=SimpleNamespace(total_deliveries=2, open_deliveries=0),
        whatsapp_summary=SimpleNamespace(has_active_whatsapp_consent=True),
        loyalty_summary=SimpleNamespace(enrolled=True, current_points=150, tier="Plata"))


class _FakePresenter:
    def __init__(self, view=None, *, raises: bool = False) -> None:
        self._view = view
        self._raises = raises
        self.calls: list[str] = []

    def customer_360(self, customer_id: str):
        self.calls.append(customer_id)
        if self._raises:
            raise RuntimeError("boom")
        return self._view


class TestPillTabBar:
    def test_first_tab_is_checked_by_default(self, app):
        bar = PillTabBar()
        bar.add_tab("resumen", "Resumen")
        bar.add_tab("identidad", "Identidad")
        buttons = list(bar._keys_by_button)
        assert buttons[0].isChecked() is True
        assert buttons[1].isChecked() is False

    def test_clicking_a_tab_emits_tab_changed(self, app):
        bar = PillTabBar()
        bar.add_tab("resumen", "Resumen")
        bar.add_tab("identidad", "Identidad")
        received = []
        bar.tab_changed.connect(received.append)
        second_button = list(bar._keys_by_button)[1]
        second_button.click()
        assert received == ["identidad"]

    def test_activate_checks_the_right_button_without_emitting(self, app):
        bar = PillTabBar()
        bar.add_tab("resumen", "Resumen")
        bar.add_tab("identidad", "Identidad")
        received = []
        bar.tab_changed.connect(received.append)
        bar.activate("identidad")
        buttons = list(bar._keys_by_button.items())
        assert dict((k, b) for b, k in buttons)["identidad"].isChecked() is True
        assert received == []  # programmatic activation, not a user click


class TestCustomerCrmPresenterCustomer360:
    def test_raises_when_unwired(self):
        presenter = CustomerCrmPresenter(session_context=_FakeSession())
        with pytest.raises(RuntimeError):
            presenter.customer_360("c1")

    def test_delegates_to_wired_service(self):
        view = _customer_360_view()

        class _FakeService:
            def get_360(self, customer_id, *, actor_user_id, team_member_ids):
                assert customer_id == "c1"
                assert actor_user_id == "u1"
                return view

        presenter = CustomerCrmPresenter(
            session_context=_FakeSession(), query_services={"customer_360": _FakeService()})
        assert presenter.customer_360("c1") is view


class TestCustomerProfilePage:
    def test_shows_placeholder_before_a_customer_is_selected(self, app):
        page = CustomerProfilePage(_FakePresenter())
        assert page._stack.currentWidget() is page._placeholder

    def test_show_customer_populates_resumen_tab(self, app):
        page = CustomerProfilePage(_FakePresenter(_customer_360_view()))
        page.show_customer("c1")
        assert page._resumen_labels["opportunities"].text() == "0"
        assert page._resumen_labels["segments"].text() == "1"
        assert page._identidad_labels["legal_name"].text() == "El Sol SA de CV"

    def test_show_customer_populates_credito_tab(self, app):
        page = CustomerProfilePage(_FakePresenter(_customer_360_view()))
        page.show_customer("c1")
        assert page._credito_labels["status"].text() == "AUTHORIZED"
        assert page._credito_labels["receivable_status"].text() == "AL_CORRIENTE"

    def test_show_customer_populates_comercial_and_integraciones(self, app):
        page = CustomerProfilePage(_FakePresenter(_customer_360_view()))
        page.show_customer("c1")
        assert page._comercial_labels["orders"].text() == "3"
        assert page._integraciones_labels["loyalty_points"].text() == "150"
        assert page._integraciones_labels["whatsapp_consent"].text() == "Sí"

    def test_show_customer_selects_resumen_tab(self, app):
        page = CustomerProfilePage(_FakePresenter(_customer_360_view()))
        page.show_customer("c1")
        assert page._stack.currentIndex() == page._tab_index["resumen"]

    def test_tab_bar_click_switches_stack(self, app):
        page = CustomerProfilePage(_FakePresenter(_customer_360_view()))
        page.show_customer("c1")
        credito_button = next(
            b for b, k in page._tab_bar._keys_by_button.items() if k == "credito")
        credito_button.click()
        assert page._stack.currentIndex() == page._tab_index["credito"]

    def test_reload_shows_error_state_when_presenter_raises(self, app):
        page = CustomerProfilePage(_FakePresenter(raises=True))
        page.show_customer("c1")
        assert not page._status.isHidden()
        assert "boom" in page._status.text()

    def test_reload_without_customer_id_is_a_noop(self, app):
        presenter = _FakePresenter(_customer_360_view())
        page = CustomerProfilePage(presenter)
        page.reload()
        assert presenter.calls == []

    def test_header_shows_customer_display_name_and_code(self, app):
        page = CustomerProfilePage(_FakePresenter(_customer_360_view()))
        page.show_customer("c1")
        assert page._header._title.text() == "Restaurante El Sol"
        assert page._header._subtitle.text() == "C-0001"
        assert page._identidad_labels["code"].text() == "C-0001"


class TestDirectoryToProfileNavigation:
    def test_double_click_opens_expediente_for_that_customer(self, app):
        capabilities = CustomerCrmCapabilities(module_view=True, clientes=True)

        class _FakePresenterWithDirectory:
            def capabilities(self):
                return capabilities

            def customers_directory(self, *, search="", status=None):
                return []

            def customer_360(self, customer_id):
                view = _customer_360_view()
                return view

        workspace = CustomersCrmWorkspace(_FakePresenterWithDirectory())
        workspace.select_route("customers.directory")
        directory_page = workspace._stack.currentWidget().findChild(QtWidgets.QScrollArea).widget()
        directory_page.entity_selected.emit("cust-42")

        assert workspace._stack.currentIndex() == workspace._route_index_by_id["customers.profile"]
        assert workspace._profile_page._customer_id == "cust-42"
