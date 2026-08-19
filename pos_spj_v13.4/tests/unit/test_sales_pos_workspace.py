"""POS-19 — SalesPosWorkspace structural tests.

Builds the REAL `SalesPosWorkspace` offscreen (mirrors `tests/unit/
test_customers_crm_ui_workspace.py`'s own convention), against the REAL
`SalesPosPresenter` class with empty `query_services`/`command_handlers` —
its own documented degrade-gracefully contract (SaleResult.fail(...,
"NOT_WIRED") / empty tuples / None) means the workspace can construct and
render safely with nothing wired, exactly the same "a component must always
have something safe to render" guarantee CRM's own presenter established.

Asserts the same structural rule the LEGACY golden-master suite protects
(`tests/visual/golden/sales_pos/test_pos_preserves_two_panel_layout.py`):
exactly one QSplitter, exactly two panels, catalog left / checkout right —
plus this module's own real vertical order inside the checkout panel (cart
before customer, matching the real legacy order SALES-1 already
documented, not the master prompt's own abstract bullet order).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication
QSplitter = QtWidgets.QSplitter

from backend.application.sales.permissions import SalesPermissions  # noqa: E402
from frontend.desktop.modules.sales_pos.components.catalog_panel import CatalogPanel  # noqa: E402
from frontend.desktop.modules.sales_pos.components.checkout_panel import CheckoutPanel  # noqa: E402
from frontend.desktop.modules.sales_pos.sales_pos_presenter import SalesPosPresenter  # noqa: E402
from frontend.desktop.modules.sales_pos.sales_pos_workspace import SalesPosWorkspace  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    def __init__(self, permissions=()):
        self.user_id = "cashier-1"
        self.active_branch_id = "branch-1"
        self.is_active = True
        self._permissions = set(permissions)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions


def _unwired_presenter(*, all_permissions=True) -> SalesPosPresenter:
    permissions = set(vars(SalesPermissions).values()) if all_permissions else set()
    permissions = {p for p in permissions if isinstance(p, str)}
    return SalesPosPresenter(session_context=_FakeSession(permissions))


class TestSalesPosWorkspaceStructure:
    def test_builds_without_a_wired_backend(self, app):
        workspace = SalesPosWorkspace(_unwired_presenter())
        assert workspace is not None

    def test_body_is_exactly_one_two_panel_splitter(self, app):
        workspace = SalesPosWorkspace(_unwired_presenter())
        splitters = workspace.findChildren(QSplitter)
        assert len(splitters) == 1
        splitter = splitters[0]
        assert splitter.count() == 2

    def test_catalog_panel_is_first_checkout_panel_is_second(self, app):
        workspace = SalesPosWorkspace(_unwired_presenter())
        splitter = workspace.findChildren(QSplitter)[0]
        assert isinstance(splitter.widget(0), CatalogPanel)
        assert isinstance(splitter.widget(1), CheckoutPanel)

    def test_cashier_bar_present_above_the_splitter(self, app):
        workspace = SalesPosWorkspace(_unwired_presenter())
        assert workspace.cashier_bar is not None
        layout = workspace.layout()
        # cashier bar must be the first item, splitter the second — same
        # "cashier bar on top" structural rule the legacy contract enforces.
        assert layout.itemAt(0).widget() is workspace.cashier_bar

    def test_checkout_panel_order_is_cart_before_customer(self, app):
        """Mirrors the REAL legacy order confirmed in SALES-1/POS-19 research
        (`sales_pos_visual_contract.md`): cart renders above the customer
        section — the opposite of the master prompt's own abstract bullet
        order — deliberately preserved here, not re-litigated."""
        workspace = SalesPosWorkspace(_unwired_presenter())
        checkout = workspace.checkout
        layout = checkout.layout()
        widgets_in_order = [layout.itemAt(i).widget() for i in range(layout.count())]
        cart_index = widgets_in_order.index(checkout.cart)
        customer_index = widgets_in_order.index(checkout.customer)
        assert cart_index < customer_index

    def test_totals_come_after_customer_and_actions_come_last(self, app):
        workspace = SalesPosWorkspace(_unwired_presenter())
        checkout = workspace.checkout
        layout = checkout.layout()
        widgets_in_order = [layout.itemAt(i).widget() for i in range(layout.count())]
        assert widgets_in_order.index(checkout.customer) < widgets_in_order.index(checkout.totals)
        assert widgets_in_order.index(checkout.totals) < widgets_in_order.index(checkout.actions)

    def test_cobrar_button_is_the_dominant_action(self, app):
        """Mirrors `test_pos_primary_charge_button_is_dominant.py`'s intent:
        Cobrar is its own row, not sharing space with the secondary actions."""
        workspace = SalesPosWorkspace(_unwired_presenter())
        actions = workspace.checkout.actions
        assert actions.btn_cobrar.text().startswith("💳 COBRAR")

    def test_action_buttons_use_the_same_variants_as_the_legacy_contract(self, app):
        workspace = SalesPosWorkspace(_unwired_presenter())
        actions = workspace.checkout.actions
        assert actions.btn_cobrar.property("variant") == "success"
        assert actions.btn_suspender.property("variant") == "warning"
        assert actions.btn_reanudar.property("variant") == "primary"
        assert actions.btn_cancelar.property("variant") == "danger"

    def test_capabilities_gate_action_buttons(self, app):
        workspace = SalesPosWorkspace(_unwired_presenter(all_permissions=False))
        actions = workspace.checkout.actions
        assert actions.btn_cobrar.isEnabled() is False
        assert actions.btn_suspender.isEnabled() is False
        assert actions.btn_devolucion.isEnabled() is False
