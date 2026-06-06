import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_phase3_component_source_files_define_required_classes() -> None:
    expected_classes = {
        "frontend/desktop/components/numeric_input.py": "class NumericInput",
        "frontend/desktop/components/money_input.py": "class MoneyInput",
        "frontend/desktop/components/quantity_input.py": "class QuantityInput",
        "frontend/desktop/components/percent_input.py": "class PercentInput",
        "frontend/desktop/components/integer_input.py": "class IntegerInput",
        "frontend/desktop/components/phone_input.py": "class PhoneInput",
        "frontend/desktop/components/search_selector.py": "class SearchSelector",
        "frontend/desktop/components/address_input.py": "class AddressInput",
        "frontend/desktop/components/status_badge.py": "class StatusBadge",
        "frontend/desktop/components/date_range_filter.py": "class DateRangeFilter",
    }

    missing = []
    for relative_path, class_name in expected_classes.items():
        content = (REPO_ROOT / "pos_spj_v13.4" / relative_path).read_text(encoding="utf-8")
        if class_name not in content:
            missing.append(f"{relative_path}: {class_name}")

    assert not missing, "Missing component classes: " + ", ".join(missing)


def _qt_components():
    qt_core = pytest.importorskip(
        "PyQt5.QtCore",
        reason="PyQt5 runtime libraries are required for UI component tests",
        exc_type=ImportError,
    )
    qt_widgets = pytest.importorskip(
        "PyQt5.QtWidgets",
        reason="PyQt5 runtime libraries are required for UI component tests",
        exc_type=ImportError,
    )
    from frontend.desktop import components

    application = qt_widgets.QApplication.instance() or qt_widgets.QApplication(sys.argv)
    return qt_core, components, application


def test_numeric_components_start_at_zero() -> None:
    _qt_core, components, _application = _qt_components()

    assert components.MoneyInput().value() == 0
    assert components.QuantityInput().value() == 0
    assert components.PercentInput().value() == 0
    assert components.IntegerInput().value() == 0


def test_phone_input_validates_whatsapp_e164_numbers() -> None:
    _qt_core, components, _application = _qt_components()
    widget = components.PhoneInput()

    widget.set_value("+5215512345678")
    assert widget.is_valid() is True

    widget.set_value("5512345678")
    assert widget.is_valid() is False


def test_search_selector_uses_provider_without_mass_combo_loading() -> None:
    _qt_core, components, _application = _qt_components()
    selector = components.SearchSelector(
        provider=lambda query: [components.SearchOption(id="p1", label=f"Producto {query}")]
    )

    selector.refresh("res")

    expected = components.SearchOption(id="p1", label="Producto res")
    item = selector._results.item(0)
    selected = item.data(qt_core.Qt.UserRole)
    assert selected == expected
    assert item.data(32) == expected

    emitted = []
    selector.selected.connect(emitted.append)
    selector._results.itemClicked.emit(item)
    assert emitted == [expected]

    selector.set_selected_label("Producto res")
    assert selector.selected_option() is None


def test_address_input_supports_map_suggestions_and_manual_fallback() -> None:
    _qt_core, components, _application = _qt_components()
    widget = components.AddressInput(
        provider=lambda query: [components.AddressSuggestion(label=f"Mapa {query}", latitude=19.43, longitude=-99.13)]
    )

    widget.refresh("Centro")
    widget._suggestions.setCurrentRow(0)
    assert widget.value() == "Mapa Centro"

    widget._manual_toggle.setChecked(True)
    widget._manual_text.setPlainText("Dirección manual")
    assert widget.value() == "Dirección manual"


def test_status_badge_and_date_range_filter_expose_standard_values() -> None:
    qt_core, components, _application = _qt_components()
    badge = components.StatusBadge("Activo", status="success")
    date_filter = components.DateRangeFilter()
    expected_range = components.DateRange(start=qt_core.QDate(2026, 1, 1), end=qt_core.QDate(2026, 1, 31))

    date_filter.set_range(expected_range)

    assert badge.property("status") == "success"
    assert date_filter.value() == expected_range
