"""CRM-32 — cross-module NavigationIntent: Customer 360's "Nueva venta"
action emits a NavigationIntent; CustomersCrmWorkspace relays it; Ventas'
`aplicar_contexto` resolves the Customer Master id back to its legacy
record."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from frontend.desktop.navigation.navigation_intent import NavigationIntent
from frontend.desktop.modules.customers_crm.customers_crm_workspace import CustomersCrmWorkspace
from frontend.desktop.modules.customers_crm.pages.customer_profile_page import (
    CustomerProfilePage,
)
from frontend.desktop.modules.customers_crm.view_models import CustomerCrmCapabilities

_ALL_TRUE = CustomerCrmCapabilities(
    module_view=True, clientes=True, prospectos=True, oportunidades=True,
    actividades=True, atencion=True, comercial=True, credito=True,
    segmentacion=True, comunicaciones=True, privacidad=True, control=True)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


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
        active_segments=[], active_tags=[],
        open_opportunities=[], open_cases=[], recent_activities=[], pending_tasks=[],
        open_duplicate_candidates=[], open_quality_issues=[], recent_history=[],
        orders_summary=SimpleNamespace(total_orders=3, open_orders=1),
        delivery_summary=SimpleNamespace(total_deliveries=2, open_deliveries=0),
        whatsapp_summary=SimpleNamespace(has_active_whatsapp_consent=True),
        loyalty_summary=SimpleNamespace(enrolled=True, current_points=150, tier="Plata"))


class _FakePresenter:
    def __init__(self, view=None, *, capabilities: CustomerCrmCapabilities | None = None) -> None:
        self._view = view
        self._capabilities = capabilities or _ALL_TRUE

    def customer_360(self, customer_id: str):
        return self._view

    def capabilities(self) -> CustomerCrmCapabilities:
        return self._capabilities


class TestNavigationIntent:
    def test_is_a_plain_dataclass_no_qt_required(self):
        intent = NavigationIntent(route="sales.new", context={"customer_id": "c1"})
        assert intent.route == "sales.new"
        assert intent.context == {"customer_id": "c1"}

    def test_context_defaults_to_empty_dict(self):
        intent = NavigationIntent(route="sales.new")
        assert intent.context == {}


class TestCustomerProfilePageNewSaleAction:
    def test_emits_navigation_intent_with_customer_id(self, app):
        page = CustomerProfilePage(_FakePresenter(_customer_360_view()))
        page.show_customer("c-123")

        received = []
        page.navigation_requested.connect(received.append)
        page._request_new_sale()

        assert len(received) == 1
        intent = received[0]
        assert isinstance(intent, NavigationIntent)
        assert intent.route == "sales.new"
        assert intent.context == {"customer_id": "c-123"}

    def test_no_emit_before_a_customer_is_selected(self, app):
        page = CustomerProfilePage(_FakePresenter())
        received = []
        page.navigation_requested.connect(received.append)
        page._request_new_sale()
        assert received == []


class TestCustomerProfilePageReceivablesAction:
    def test_emits_finance_receivables_navigation_intent(self, app):
        page = CustomerProfilePage(_FakePresenter(_customer_360_view()))
        page.show_customer("c-456")

        received = []
        page.navigation_requested.connect(received.append)
        page._request_receivables()

        assert len(received) == 1
        intent = received[0]
        assert intent.route == "finance.receivables"
        assert intent.context == {"customer_id": "c-456"}

    def test_no_emit_before_a_customer_is_selected(self, app):
        page = CustomerProfilePage(_FakePresenter())
        received = []
        page.navigation_requested.connect(received.append)
        page._request_receivables()
        assert received == []


class TestCustomersCrmWorkspaceRelaysNavigationIntent:
    def test_profile_page_navigation_bubbles_up_to_workspace(self, app):
        workspace = CustomersCrmWorkspace(_FakePresenter(_customer_360_view()))
        workspace.select_route("customers.profile")
        profile_page = workspace._profile_page
        assert isinstance(profile_page, CustomerProfilePage)

        received = []
        workspace.navigation_requested.connect(received.append)
        profile_page.show_customer("c-999")
        profile_page._request_new_sale()

        assert len(received) == 1
        assert received[0].context == {"customer_id": "c-999"}
