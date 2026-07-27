import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_address_click_selection_updates_value_coords_and_verified() -> None:
    try:
        from PyQt5.QtWidgets import QApplication, QListWidgetItem
    except ImportError as exc:
        pytest.skip(f"PyQt runtime unavailable: {exc}")

    from modulos.components.address_autocomplete_input import AddressAutocompleteInput

    app = QApplication.instance() or QApplication([])
    widget = AddressAutocompleteInput(geocoding_service=object())
    item = QListWidgetItem("Av. Reforma 123")
    item.setData(32, {"label": "Av. Reforma 123", "lat": 19.4326, "lng": -99.1332, "place_id": "mx-1"})

    widget._select_suggestion(item)

    assert widget.value() == "Av. Reforma 123"
    assert widget.coords() == (19.4326, -99.1332)
    assert widget.place_id() == "mx-1"
    assert widget.address_verified() is True
    assert not widget._suggestions.isVisible()

    widget._search_box.setText("Av. Reforma editada")
    assert widget.address_verified() is False
    assert widget.coords() is None
    app.processEvents()
    widget.deleteLater()
