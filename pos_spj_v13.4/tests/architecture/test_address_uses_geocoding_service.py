from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")
ADDRESS_COMPONENT = Path("pos_spj_v13.4/modulos/components/address_autocomplete_input.py")
GEOCODING_SERVICE = Path("pos_spj_v13.4/core/services/geocoding_service.py")


def test_configuracion_uses_async_address_autocomplete_component() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")
    component = ADDRESS_COMPONENT.read_text(encoding="utf-8")
    service = GEOCODING_SERVICE.read_text(encoding="utf-8")

    assert "AddressAutocompleteInput" in content
    assert "AddressInput" not in content
    assert "lambda _query: []" not in component
    assert "GeocodingService" in component
    assert "QRunnable" in component
    assert "QThreadPool" in component
    assert "request_id" in component
    assert "_cache" in component
    assert "MapboxAddressProvider" in service
    assert "NominatimProvider" in service
