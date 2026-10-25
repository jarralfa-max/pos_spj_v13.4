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
    def test_cart_totals_stay_left_of_configured_media(self, app):
        from PyQt5.QtCore import QPoint
        window = CustomerDisplayWindow()
        try:
            window.resize(1280, 720)
            window.render_content("CART", dict(_CART_CONTENT, SCALE="Báscula: 0.850 kg", POINTS="Puntos estimados: 45"))
            window.render_idle_ad("TEXT", "Promo", "Oferta vigente", during_sale=True)
            app.processEvents()
            media_left = window._media_region.mapTo(window, QPoint(0, 0)).x()
            for widget in (window._items_area, window._totals_labels["TOTAL"], window._scale_label, window._points_label):
                assert widget.mapTo(window, widget.rect().bottomRight()).x() < media_left
            assert window._points_label.width() >= window._scale_label.width() - 1
        finally:
            window.close()

    def test_completion_uses_forest_brand_surface_and_restores_cart(self, app):
        from frontend.desktop.themes.theme_manager import ThemeManager
        from frontend.desktop.themes.brand_palette import BrandColors
        from PyQt5.QtGui import QColor
        ThemeManager.instance().apply(app, "light")
        window = CustomerDisplayWindow()
        try:
            content = {"MESSAGE": "¡Gracias por tu compra!\n¡Te esperamos pronto!", "TOTAL": "459.75", "POINTS": "+45 puntos acreditados"}
            window.render_content("THANK_YOU", content)
            window.render_content("THANK_YOU", content)
            app.processEvents()
            assert window.grab().toImage().pixelColor(2, 2) == QColor(BrandColors.FOREST_GREEN)
            assert "Pago confirmado" in window._totals_labels["TOTAL"].text()
            assert window._totals_labels["TOTAL"].y() < window._points_label.y() < window._farewell_label.y()
            window.render_content("CART", _CART_CONTENT)
            assert window._items_area.isVisible()
        finally:
            window.close()

    def test_ad_remains_visible_while_cart_changes_and_stops_at_payment(self, app):
        window = CustomerDisplayWindow()
        try:
            window.render_content("CART", _CART_CONTENT)
            window.render_idle_ad("TEXT", "Promoción", "Oferta vigente", during_sale=True)
            window.render_content("CART", dict(_CART_CONTENT, TOTAL="250"))
            assert window._media_region.isVisible()
            assert window._ad_label.text() == "Oferta vigente"
            assert window._items_area.isVisible()
            window.render_content("PAYMENT_PENDING", {"TOTAL": "250", "PAYMENT": "Procesando"})
            assert not window._media_region.isVisible()
            assert "250" in window._totals_labels["TOTAL"].text()
        finally:
            window.close()

    def test_live_scale_is_independent_of_cart_and_hidden_section_stays_hidden(self, app):
        window = CustomerDisplayWindow()
        gateway = QtCustomerDisplayGateway(window)
        try:
            content = dict(_CART_CONTENT, SCALE="Báscula: 0.850 kg · estable")
            content["ITEMS"] = [{"name": "Alas", "quantity": "6.500", "line_total": "520"}]
            gateway.push(display_id="display-test", mode=CustomerDisplayMode.CART, content=content)
            assert "0.850" in window._scale_label.text()
            assert "6.500" not in window._scale_label.text()
            gateway.update_scale("Báscula: lectura vencida")
            assert "0.850" not in window._scale_label.text()
            gateway.push(display_id="display-test", mode=CustomerDisplayMode.CART, content=_CART_CONTENT)
            gateway.update_scale("Báscula: 0.850 kg · estable")
            assert not window._scale_label.isVisible()
        finally:
            window.close()

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

    def test_html_content_renders_an_honest_placeholder_not_fabricated_rendering(self, app):
        window = CustomerDisplayWindow()
        try:
            window.render_idle_ad("HTML", "Promo", "<html>ignored</html>")
            assert window._ad_label.text() == "Promo (HTML)"
            assert "<html>" not in window._ad_label.text()
        finally:
            window.close()

    @pytest.mark.parametrize("content_type", ["IMAGE", "VIDEO"])
    def test_media_without_its_file_says_so_instead_of_painting_anything(self, app, content_type):
        """Desde 2026-10-08 imagen y video se muestran de verdad (migración
        313); si el archivo ya no está, la pantalla lo dice — no inventa nada
        ni muestra el id del archivo."""
        window = CustomerDisplayWindow()
        try:
            window.render_idle_ad(content_type, "Promo", "01a00000-0000-7000-8000-000000000000", None)
            assert window._ad_label.text() == "Promo (el archivo ya no está disponible)"
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


class TestVideoBackend:
    def test_widget_player_does_not_force_surface_backend(self, app, monkeypatch):
        from PyQt5 import QtMultimedia
        real_player = QtMultimedia.QMediaPlayer
        requested_flags = []

        def create_player(parent=None, flags=real_player.Flags()):
            requested_flags.append(flags)
            return real_player(parent, flags)

        create_player.VideoSurface = real_player.VideoSurface
        monkeypatch.setattr(QtMultimedia, "QMediaPlayer", create_player)
        window = CustomerDisplayWindow()
        try:
            window._play_video("unavailable-test-video.mp4")
            assert not (requested_flags[0] & real_player.VideoSurface)
        finally:
            window.close()

    @pytest.mark.skipif(os.name != "nt", reason="Windows multimedia preference")
    def test_windows_prefers_media_foundation_without_overriding_explicit_choice(self, app, monkeypatch):
        monkeypatch.delenv("QT_MULTIMEDIA_PREFERRED_PLUGINS", raising=False)
        window = CustomerDisplayWindow()
        try:
            window._play_video("unavailable-test-video.mp4")
            assert os.environ.get("QT_MULTIMEDIA_PREFERRED_PLUGINS") == "windowsmediafoundation"
            monkeypatch.setenv("QT_MULTIMEDIA_PREFERRED_PLUGINS", "directshow")
            window._play_video("unavailable-test-video.mp4")
            assert os.environ["QT_MULTIMEDIA_PREFERRED_PLUGINS"] == "directshow"
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
