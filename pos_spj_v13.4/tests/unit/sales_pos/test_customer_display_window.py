"""SET-17 — `CustomerDisplayWindow.render_content()` and
`QtCustomerDisplayGateway.push()`. Unlike SET-14's label printers,
`CustomerDisplayGatewayPort`'s own docstring names a real second-screen
window as sufficient validation — a real (offscreen) `QWidget`, not a
mock, backs these tests.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.domain.customer_display.enums import CustomerDisplayMode  # noqa: E402
from frontend.desktop.modules.sales_pos.customer_display_window import (  # noqa: E402
    CustomerDisplayWindow,
    QtCustomerDisplayGateway,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


_CART_CONTENT = {
    "CUSTOMER_NAME": "Juan Pérez",
    "ITEMS": [{"name": "Bistec", "quantity": "2", "unit_price": "100", "line_total": "200"}],
    "SUBTOTAL": "200",
    "TOTAL": "200",
    "MESSAGE": "",
}


class TestRenderContent:
    def test_renders_only_the_keys_present_in_content(self, app):
        window = CustomerDisplayWindow()
        try:
            window.render_content("CART", _CART_CONTENT)
            assert window._customer_name_label.text() == "Juan Pérez"
            assert window._totals_labels["TOTAL"].isVisible()
            assert window._totals_labels["DISCOUNT"].isVisible() is False
        finally:
            window.close()

    def test_a_disabled_or_omitted_section_shows_nothing_fabricated(self, app):
        window = CustomerDisplayWindow()
        try:
            window.render_content("IDLE", {})
            assert window._customer_name_label.text() == ""
            for label in window._totals_labels.values():
                assert label.isVisible() is False
            assert window._message_label.text() == ""
        finally:
            window.close()

    def test_items_are_rendered_as_real_line_widgets(self, app):
        window = CustomerDisplayWindow()
        try:
            window.render_content("CART", _CART_CONTENT)
            assert window._items_layout.count() == 1
        finally:
            window.close()

    def test_re_render_clears_previous_items(self, app):
        window = CustomerDisplayWindow()
        try:
            window.render_content("CART", _CART_CONTENT)
            window.render_content("IDLE", {})
            assert window._items_layout.count() == 0
        finally:
            window.close()

    def test_message_section_renders_the_thank_you_text(self, app):
        window = CustomerDisplayWindow()
        try:
            window.render_content("THANK_YOU", {"MESSAGE": "¡Gracias por su compra!"})
            assert window._message_label.text() == "¡Gracias por su compra!"
        finally:
            window.close()


class TestRenderIdleAd:
    """SET-18 cutover — `render_idle_ad()`."""

    def test_text_content_renders_the_real_body(self, app):
        window = CustomerDisplayWindow()
        try:
            window.render_idle_ad("TEXT", "Promo", "2x1 en refrescos")
            assert window._ad_label.text() == "2x1 en refrescos"
            assert window._ad_label.isVisible() is True
        finally:
            window.close()

    @pytest.mark.parametrize("content_type", ["IMAGE", "VIDEO", "HTML"])
    def test_non_text_content_renders_an_honest_placeholder_not_fabricated_rendering(self, app, content_type):
        window = CustomerDisplayWindow()
        try:
            window.render_idle_ad(content_type, "Promo", "<html>ignored</html>")
            assert window._ad_label.text() == f"Promo ({content_type})"
            assert "<html>" not in window._ad_label.text()
        finally:
            window.close()

    def test_render_content_hides_the_ad_label(self, app):
        """Sale-state and idle-ad content are mutually exclusive on
        screen — `render_content()` (SET-17's own path) must hide any
        currently-showing ad."""
        window = CustomerDisplayWindow()
        try:
            window.render_idle_ad("TEXT", "Promo", "2x1")
            assert window._ad_label.isVisible() is True
            window.render_content("CART", _CART_CONTENT)
            assert window._ad_label.isVisible() is False
        finally:
            window.close()


class TestRealTopLevelWindowWhenParented:
    """SET-18 repegado: real bug found while smoke-testing the ad
    rotation — `SalesPosWorkspace` constructs this window with itself as
    `parent` (for Qt-managed lifetime), but a plain `QWidget(parent)` is
    an ordinary embedded child by default (`isWindow()` False), so it
    never actually appeared as an independent window and every child's
    `isVisible()` silently reported False. Fixed via the `Qt.Window`
    flag; this test locks the fix in."""

    def test_is_a_real_top_level_window_even_when_given_a_parent(self, app):
        from PyQt5.QtWidgets import QWidget

        parent = QWidget()
        try:
            window = CustomerDisplayWindow(parent)
            try:
                assert window.isWindow() is True
            finally:
                window.close()
        finally:
            parent.close()


class TestQtCustomerDisplayGateway:
    def test_push_delegates_to_the_window_with_mode_value_and_content(self, app):
        window = CustomerDisplayWindow()
        try:
            gateway = QtCustomerDisplayGateway(window)
            gateway.push(display_id="disp-1", mode=CustomerDisplayMode.CART, content=_CART_CONTENT)
            assert window._customer_name_label.text() == "Juan Pérez"
        finally:
            window.close()
