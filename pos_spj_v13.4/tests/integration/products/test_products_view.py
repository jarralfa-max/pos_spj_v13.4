"""Navegación sidebar enterprise — SideNav + ProductsView (lazy + resiliente)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

from frontend.desktop.components import SideNav  # noqa: E402
from frontend.desktop.modules.products.products_view import ProductsView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ── SideNav ──────────────────────────────────────────────────────────────────
def test_side_nav_emits_navigated(app):
    nav = SideNav()
    seen = []
    nav.navigated.connect(seen.append)
    nav.add_section("Uno")
    nav.add_section("Dos")
    nav.select(1)
    assert nav.count() == 2 and seen[-1] == 1


# ── ProductsView ─────────────────────────────────────────────────────────────
class _Page(QWidget):
    instances = 0

    def __init__(self, presenter):
        super().__init__()
        _Page.instances += 1
        self._presenter = presenter


def _factory(_presenter):
    return _Page(_presenter)


def test_view_builds_sidebar_and_selects_first(app):
    _Page.instances = 0
    view = ProductsView(object(), [(_factory, "A"), (_factory, "B"),
                                    (_factory, "C")])
    assert view.nav.count() == 3
    assert view.stack.count() == 3
    assert view.stack.currentIndex() == 0
    # Sólo la primera sección se construyó (perezoso).
    assert _Page.instances == 1


def test_view_lazy_builds_on_navigation(app):
    _Page.instances = 0
    view = ProductsView(object(), [(_factory, "A"), (_factory, "B")])
    assert _Page.instances == 1
    view.nav.select(1)
    assert view.stack.currentIndex() == 1
    assert _Page.instances == 2  # la segunda se construyó al navegar
    # Re-visitar no reconstruye.
    view.nav.select(0)
    view.nav.select(1)
    assert _Page.instances == 2


def test_view_is_resilient_to_failing_page(app):
    def _boom(_presenter):
        raise RuntimeError("falla intencional")

    view = ProductsView(object(), [(_boom, "Rota")])
    # El slot muestra un aviso en vez de propagar la excepción.
    slot = view.stack.widget(0)
    child = slot.layout().itemAt(0).widget()
    assert isinstance(child, QLabel) and "No disponible" in child.text()
