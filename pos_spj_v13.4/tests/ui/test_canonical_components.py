"""FASE DS-3/DS-4 — canonical component smoke + contract tests.

Runs headless (offscreen Qt). Verifies components construct under both themes,
carry the expected objectName/variant hooks, and honor their contracts.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from frontend.desktop.components import (  # noqa: E402
    ConfirmationDialog,
    Icons,
    KPIBar,
    KPICard,
    KPIDTO,
    KPIState,
    PageHeader,
    SectionCard,
    StandardDialog,
    StateWidget,
    TimeInput,
    TimeRangeInput,
    ViewState,
    create_icon_button,
    create_primary_button,
    create_state_widget,
)
from frontend.desktop.themes.theme_manager import ThemeManager  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture(params=["light", "dark"])
def themed_app(app, request):
    ThemeManager.instance().apply(app, request.param)
    return app


def test_buttons_carry_variant_and_no_inline_style(themed_app):
    btn = create_primary_button(text="Guardar")
    assert btn.property("variant") == "primary"
    assert btn.objectName() == "standardButton"
    assert btn.styleSheet() == ""  # look comes from global QSS, not inline


def test_icon_button_requires_tooltip(themed_app):
    with pytest.raises(ValueError):
        create_icon_button(None, Icons.ADD, tooltip="")
    btn = create_icon_button(None, Icons.ADD, tooltip="Agregar")
    assert btn.accessibleName()  # accessible name is mandatory
    assert btn.toolTip()


def test_page_header_builds_with_actions(themed_app):
    header = PageHeader(title="Configuración", subtitle="Empresa y usuarios",
                        icon=Icons.SETTINGS)
    header.add_action(create_primary_button(text="Nuevo"))
    assert header.objectName() == "pageHeader"


def test_kpi_card_is_presentation_only(themed_app):
    dto = KPIDTO(key="sales", title="Ventas netas", value="$125,430.00",
                 icon=Icons.SALES, variant="success",
                 trend_value="8.4%", trend_direction="up",
                 trend_label="vs. periodo anterior", tooltip="Ventas netas.")
    card = KPICard(dto)
    assert card.property("variant") == "success"
    assert "Ventas netas" in card.accessibleName()


def test_kpi_card_loading_state_hides_value(themed_app):
    dto = KPIDTO(key="k", title="Cargando", value="$0.00", state=KPIState.LOADING)
    card = KPICard(dto)
    # value label must not show a misleading zero during loading
    assert "$0.00" not in card.accessibleName()


def test_kpi_bar_renders_all_cards(themed_app):
    dtos = [KPIDTO(key=str(i), title=f"K{i}", value=str(i)) for i in range(5)]
    bar = KPIBar(cards=dtos, responsive=False)
    assert bar._grid.count() == 5


def test_section_card_variant(themed_app):
    card = SectionCard(title="Datos de la empresa")
    assert card.property("cardVariant") == "section"


@pytest.mark.parametrize("state", [ViewState.LOADING, ViewState.EMPTY,
                                    ViewState.ERROR, ViewState.NO_PERMISSION,
                                    ViewState.OFFLINE, ViewState.STALE,
                                    ViewState.PARTIAL_DATA])
def test_state_widgets_build_with_message(themed_app, state):
    widget = create_state_widget(state)
    assert isinstance(widget, StateWidget)
    assert widget.property("state") == state
    assert widget.accessibleName()


def test_dialogs_build(themed_app):
    dlg = StandardDialog(title="Título")
    dlg.add_button_box()
    assert dlg.objectName() == "standardDialog"
    conf = ConfirmationDialog(title="Confirmar", message="¿Continuar?")
    assert conf.objectName() == "standardDialog"


class TestTimeInput:
    def test_accepts_and_returns_hh_mm(self, themed_app):
        t = TimeInput()
        assert t.set_time_text("00:00") is True
        assert t.time_text() == "00:00"
        assert t.set_time_text("08:00") is True
        assert t.time_text() == "08:00"
        assert t.set_time_text("23:59") is True
        assert t.time_text() == "23:59"

    def test_rejects_malformed(self, themed_app):
        t = TimeInput()
        t.set_time_text("08:00")
        assert t.set_time_text("24:00") is False
        assert t.set_time_text("8 AM") is False
        assert t.time_text() == "08:00"  # unchanged after rejected input

    def test_preserves_leading_zero(self, themed_app):
        t = TimeInput()
        t.set_time_text("08:05")
        assert t.time_text() == "08:05"


class TestTimeRangeInput:
    def test_valid_day_range(self, themed_app):
        r = TimeRangeInput()
        r.set_range("08:00", "20:00")
        assert r.validate() is None

    def test_overnight_requires_flag(self, themed_app):
        r = TimeRangeInput(allow_overnight=False)
        r.set_range("22:00", "06:00")
        assert r.validate() is not None
        r2 = TimeRangeInput(allow_overnight=True)
        r2.set_range("22:00", "06:00")
        assert r2.validate() is None

    def test_equal_times_rejected_without_silent_swap(self, themed_app):
        r = TimeRangeInput()
        r.set_range("09:00", "09:00")
        assert r.validate() is not None
        assert r.start_text() == "09:00" and r.end_text() == "09:00"
