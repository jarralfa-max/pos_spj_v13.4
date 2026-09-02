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


class TestCustomerDisplayToggle:
    """SET-17 — the cashier-bar toggle owns a real (offscreen)
    `CustomerDisplayWindow`; `_refresh()` pushes to it only while open, and
    a push failure never blocks the cashier's real workflow (same
    best-effort discipline every `_try_*` integration helper already
    established for SET-12/13/15)."""

    def test_toggle_button_opens_and_closes_the_window(self, app):
        workspace = SalesPosWorkspace(_unwired_presenter())
        assert workspace._customer_display_window is None

        workspace.cashier_bar._btn_customer_display.setChecked(True)
        assert workspace._customer_display_window is not None

        workspace.cashier_bar._btn_customer_display.setChecked(False)
        assert workspace._customer_display_window is None

    def test_refresh_pushes_to_the_display_only_while_open(self, app):
        calls = []
        presenter = SalesPosPresenter(
            session_context=_FakeSession({SalesPermissions.VIEW}),
            command_handlers={"push_customer_display": lambda **kw: calls.append(kw)})
        workspace = SalesPosWorkspace(presenter)

        workspace._refresh()
        assert calls == []

        workspace.cashier_bar._btn_customer_display.setChecked(True)
        assert len(calls) == 1  # opening the display pushes immediately

        workspace._refresh()
        assert len(calls) == 2

        workspace.cashier_bar._btn_customer_display.setChecked(False)
        workspace._refresh()
        assert len(calls) == 2  # closed — no further pushes

    def test_a_push_failure_never_blocks_refresh(self, app):
        def _raise(**kwargs):
            raise RuntimeError("pantalla desconectada")

        presenter = SalesPosPresenter(
            session_context=_FakeSession({SalesPermissions.VIEW}),
            command_handlers={"push_customer_display": _raise})
        workspace = SalesPosWorkspace(presenter)
        workspace.cashier_bar._btn_customer_display.setChecked(True)

        workspace._refresh()  # must not raise


class _FakeAdvertisingQueryService:
    def __init__(self, ads=()) -> None:
        self._ads = list(ads)

    def resolve_active_ads(self, mode):
        return tuple(self._ads)


def _ad(placement_id="placement-1", duration_seconds=2, title="Promo", body="2x1"):
    from backend.application.customer_display.dto import ResolvedAdDTO

    return ResolvedAdDTO(
        placement_id=placement_id, campaign_id="campaign-1", content_id="content-1", title=title,
        content_type="TEXT", body=body, duration_seconds=duration_seconds,
    )


class TestAdvertisingRotation:
    """SET-18 cutover — `_on_ad_timer_tick()`. Ticks are invoked directly,
    never via a real `QTimer` firing, same discipline as every other
    workspace test in this file."""

    def _presenter(self, *, ads=(), record_calls=None, push_calls=None):
        record_calls = record_calls if record_calls is not None else []
        push_calls = push_calls if push_calls is not None else []
        return SalesPosPresenter(
            session_context=_FakeSession({SalesPermissions.VIEW}),
            query_services={"advertising": _FakeAdvertisingQueryService(ads)},
            command_handlers={
                "push_customer_display": lambda **kw: push_calls.append(kw),
                "record_ad_impression": lambda **kw: record_calls.append(kw),
            },
        )

    def test_first_tick_while_idle_shows_the_ad_immediately(self, app):
        presenter = self._presenter(ads=[_ad()])
        workspace = SalesPosWorkspace(presenter)
        workspace.cashier_bar._btn_customer_display.setChecked(True)

        workspace._on_ad_timer_tick()

        assert workspace._customer_display_window._ad_label.text() == "2x1"
        assert workspace._customer_display_window._ad_label.isVisible() is True

    def test_never_shows_an_ad_while_the_cart_has_real_lines(self, app):
        presenter = self._presenter(ads=[_ad()])
        workspace = SalesPosWorkspace(presenter)
        workspace._cart_is_idle = False
        workspace.cashier_bar._btn_customer_display.setChecked(True)

        workspace._on_ad_timer_tick()

        assert workspace._ad_rotation == []
        assert workspace._customer_display_window._ad_label.isVisible() is False

    def test_records_a_real_impression_when_the_duration_elapses(self, app):
        record_calls = []
        presenter = self._presenter(ads=[_ad(duration_seconds=2)], record_calls=record_calls)
        workspace = SalesPosWorkspace(presenter)
        workspace.cashier_bar._btn_customer_display.setChecked(True)

        workspace._on_ad_timer_tick()  # tick 0: resolves + shows, elapsed stays 0
        assert record_calls == []
        workspace._on_ad_timer_tick()  # tick 1: elapsed=1, not yet
        assert record_calls == []
        workspace._on_ad_timer_tick()  # tick 2: elapsed=2 >= duration -> records + rotates
        assert record_calls == [{"placement_id": "placement-1", "duration_shown_seconds": 2}]

    def test_rotates_to_the_next_ad_and_re_resolves_on_full_cycle(self, app):
        first = _ad(placement_id="p1", duration_seconds=1, title="First", body="uno")
        second = _ad(placement_id="p2", duration_seconds=1, title="Second", body="dos")
        presenter = self._presenter(ads=[first, second])
        workspace = SalesPosWorkspace(presenter)
        workspace.cashier_bar._btn_customer_display.setChecked(True)

        workspace._on_ad_timer_tick()  # shows "uno"
        assert workspace._customer_display_window._ad_label.text() == "uno"
        workspace._on_ad_timer_tick()  # elapsed=1 >= 1 -> rotates to "dos"
        assert workspace._customer_display_window._ad_label.text() == "dos"
        workspace._on_ad_timer_tick()  # elapsed=1 >= 1 -> wraps, re-resolves, back to "uno"
        assert workspace._customer_display_window._ad_label.text() == "uno"

    def test_a_resolve_failure_never_raises_out_of_the_tick(self, app):
        class _RaisingQueryService:
            def resolve_active_ads(self, mode):
                raise RuntimeError("boom")

        presenter = SalesPosPresenter(
            session_context=_FakeSession({SalesPermissions.VIEW}),
            query_services={"advertising": _RaisingQueryService()},
            command_handlers={"push_customer_display": lambda **kw: None})
        workspace = SalesPosWorkspace(presenter)
        workspace.cashier_bar._btn_customer_display.setChecked(True)

        workspace._on_ad_timer_tick()  # must not raise

    def test_toggling_the_display_off_stops_the_timer(self, app):
        presenter = self._presenter(ads=[_ad()])
        workspace = SalesPosWorkspace(presenter)
        workspace.cashier_bar._btn_customer_display.setChecked(True)
        assert workspace._ad_timer.isActive() is True

        workspace.cashier_bar._btn_customer_display.setChecked(False)
        assert workspace._ad_timer.isActive() is False
