"""P1-A — KPIs completos + refresco en vivo (§8.1/§8.2/§8.3/§8.4)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from frontend.desktop.components import KPIBar, KPIDTO  # noqa: E402
from frontend.desktop.components.kpi_card import KPICard, KPIState  # noqa: E402
from frontend.desktop.modules.products.products_view import ProductsView  # noqa: E402


@pytest.fixture(autouse=True)
def _app():
    return QApplication.instance() or QApplication([])


# ── §8.4 update-by-key ────────────────────────────────────────────────────────
def test_kpibar_updates_in_place_when_keys_match():
    bar = KPIBar()
    bar.set_cards([KPIDTO(key="a", title="A", value="1"),
                   KPIDTO(key="b", title="B", value="2")])
    cards_before = list(bar._widgets)
    assert [c.key for c in cards_before] == ["a", "b"]
    # mismo conjunto de keys → actualiza en sitio (mismos objetos widget)
    bar.set_cards([KPIDTO(key="a", title="A", value="9"),
                   KPIDTO(key="b", title="B", value="8")])
    assert bar._widgets is not None
    assert [id(c) for c in bar._widgets] == [id(c) for c in cards_before]
    assert cards_before[0]._value.text() == "9"


def test_kpibar_rebuilds_when_keys_change():
    bar = KPIBar()
    bar.set_cards([KPIDTO(key="a", title="A", value="1")])
    before = list(bar._widgets)
    bar.set_cards([KPIDTO(key="x", title="X", value="1")])  # key distinto → rebuild
    assert [id(c) for c in bar._widgets] != [id(c) for c in before]
    assert bar._widgets[0].key == "x"


def test_kpicard_state_placeholder():
    card = KPICard(KPIDTO(key="k", title="T", value="5", state=KPIState.EMPTY))
    assert card._value.text() == "—"  # EMPTY → placeholder
    card.update(KPIDTO(key="k", title="T", value="5", state=KPIState.READY))
    assert card._value.text() == "5"


# ── §8.3 señal central product_data_changed ──────────────────────────────────
class _CountingOverview:
    def __init__(self):
        self.refreshed = 0

    def set_data_changed_signal(self, sig):
        sig.connect(self._on)

    def _on(self):
        self.refreshed += 1

    def refresh(self):
        pass


class _Emitter:
    def __init__(self):
        self._sig = None

    def set_data_changed_signal(self, sig):
        self._sig = sig

    def emit(self):
        self._sig.emit()

    def refresh(self):
        pass


def test_central_signal_refreshes_display_page():
    from PyQt5.QtWidgets import QWidget

    overview = _CountingOverview()
    emitter = _Emitter()

    def ov_factory(_p):
        w = QWidget(); w.set_data_changed_signal = overview.set_data_changed_signal
        w.refresh = overview.refresh
        return w

    def em_factory(_p):
        w = QWidget(); w.set_data_changed_signal = emitter.set_data_changed_signal
        w.refresh = emitter.refresh
        return w

    view = ProductsView(presenter=object(), specs=[(ov_factory, "Resumen"),
                                                    (em_factory, "Catálogo")])
    view._on_nav(1)  # construye la página emisora (cablea la señal)
    emitter.emit()
    assert overview.refreshed >= 1
