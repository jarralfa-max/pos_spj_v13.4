"""P0-A slice 3 — los datos (KPIs) se refrescan al re-navegar, sin reiniciar la app.

Reproducido: `ProductsView` construía cada página una sola vez y `_on_nav` sólo
cambiaba el índice; volver al Resumen tras crear/activar un producto no re-leía los
KPIs. Ahora re-navegar a una página ya construida invoca su `refresh()`.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

from frontend.desktop.modules.products.products_view import ProductsView  # noqa: E402


class _CountingPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.refresh_count = 0

    def refresh(self):
        self.refresh_count += 1


@pytest.fixture(autouse=True)
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


def _page_factory():
    return _CountingPage()


def test_revisiting_page_triggers_refresh():
    specs = [(lambda _p: _page_factory(), "Resumen"),
             (lambda _p: _page_factory(), "Catálogo")]
    view = ProductsView(presenter=object(), specs=specs)
    # página 0 construida en el arranque (nav.select(0))
    page0 = view.stack.widget(0).layout().itemAt(0).widget()
    assert isinstance(page0, _CountingPage)
    base = page0.refresh_count
    # navegar a 1 (construye) y volver a 0 (re-navegación → refresh)
    view._on_nav(1)
    view._on_nav(0)
    assert page0.refresh_count == base + 1
    # otra vuelta más → otro refresh
    view._on_nav(1)
    view._on_nav(0)
    assert page0.refresh_count == base + 2


def test_refresh_failure_does_not_break_navigation():
    class _BoomPage(QWidget):
        def refresh(self):
            raise RuntimeError("boom")

    specs = [(lambda _p: _BoomPage(), "A"), (lambda _p: QLabel("B"), "B")]
    view = ProductsView(presenter=object(), specs=specs)
    view._on_nav(1)
    # re-navegar a la página que falla en refresh no debe lanzar
    view._on_nav(0)
    assert view.stack.currentIndex() == 0
