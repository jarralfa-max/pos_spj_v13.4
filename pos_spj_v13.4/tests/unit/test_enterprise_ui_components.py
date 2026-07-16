from __future__ import annotations

import os
from decimal import Decimal

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtCore = pytest.importorskip("PyQt5.QtCore", exc_type=ImportError)
QtWidgets = pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)
Qt = QtCore.Qt
QApplication = QtWidgets.QApplication
QComboBox = QtWidgets.QComboBox
QLabel = QtWidgets.QLabel
<<<<<<< HEAD
=======
QLineEdit = QtWidgets.QLineEdit
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23

from frontend.desktop.components import (  # noqa: E402
    DecimalInput,
    HtmlChartView,
    MonthInput,
    SearchableComboBox,
    StandardDialog,
<<<<<<< HEAD
=======
    StandardForm,
    FormField,
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
    TimeInput,
    TimeRangeInput,
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_time_input_uses_hh_mm_contract(app: QApplication) -> None:
    widget = TimeInput()

    widget.set_time_text("00:00")
    assert widget.time_text() == "00:00"

    widget.set_time_text("08:00")
    assert widget.time_text() == "08:00"

    widget.set_time_text("23:59")
    assert widget.time_text() == "23:59"

    for invalid in ("24:00", "8 AM", "8", "08.00"):
        with pytest.raises(ValueError):
            widget.set_time_text(invalid)


def test_time_range_input_validates_order_and_overnight(app: QApplication) -> None:
    range_input = TimeRangeInput(start_time="08:00", end_time="20:00")
    assert range_input.range_text() == ("08:00", "20:00")

    with pytest.raises(ValueError):
        TimeRangeInput(start_time="22:00", end_time="06:00")

    overnight = TimeRangeInput(start_time="22:00", end_time="06:00", allow_overnight=True)
    assert overnight.range_text() == ("22:00", "06:00")


def test_month_input_returns_accounting_period_text(app: QApplication) -> None:
    widget = MonthInput()
    widget.set_period_text("2026-07")

    assert widget.period_text() == "2026-07"

    with pytest.raises(ValueError):
        widget.set_period_text("07/2026")


def test_searchable_combo_uses_contains_search_and_uuid_data(app: QApplication) -> None:
    combo = SearchableComboBox()
    combo.set_options((("018f9a8a-aaaa-bbbb-cccc-000000000001", "Sucursal Centro"),))
    combo.setCurrentIndex(1)

    assert combo.isEditable()
    assert combo.insertPolicy() == QComboBox.NoInsert
    assert combo.completer() is not None
    assert combo.completer().filterMode() == Qt.MatchContains
    assert combo.selected_id() == "018f9a8a-aaaa-bbbb-cccc-000000000001"


def test_decimal_input_returns_decimal_not_float(app: QApplication) -> None:
    widget = DecimalInput(decimals=3)
    widget.set_decimal_value("12.500")

    assert widget.decimal_value() == Decimal("12.5")


<<<<<<< HEAD
=======
def test_standard_form_field_validation_state_and_focus(app: QApplication) -> None:
    form = StandardForm()
    field = form.add_field(
        "name",
        FormField("Nombre", QLineEdit(), helper_text="Ej. Ana", required=True),
    )

    form.set_error("name", "Captura el nombre.")

    assert field.error.isVisible()
    assert form.has_errors()
    form.clear_errors()
    assert not form.has_errors()


>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
def test_standard_dialog_and_html_chart_are_semantic_components(app: QApplication) -> None:
    dialog = StandardDialog(title="Confirmar", description="Revisa los datos.", content=QLabel("Contenido"))
    chart = HtmlChartView(accessibility_summary="Ventas por día")
    chart.set_chart_html("<div id='chart'></div>", accessibility_summary="Ventas por día")

    assert dialog.property("component") == "standardDialog"
    assert chart.property("renderer") == "html_js"
    assert chart.chart_html() == "<div id='chart'></div>"
