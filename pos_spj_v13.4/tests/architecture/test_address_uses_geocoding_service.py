"""Guardia del estándar de direcciones.

ESTE ARCHIVO APUNTABA A TRES ARCHIVOS BORRADOS
-----------------------------------------------
Leía `modulos/configuracion.py`, `modulos/components/address_autocomplete_input.py`
y `core/services/geocoding_service.py`, que se fueron con el legacy, y fallaba
siempre con `FileNotFoundError`. Era lo único que quedaba de la geocodificación
con Mapbox del commit `42f0ed01`, que se perdió en ese borrado.

Ahora vigila el estándar que la reemplaza (decisiones del usuario, 2026-09-17):
un solo componente para todos los módulos, Mapbox configurable desde
Configuración → Integraciones, respaldo a Nominatim y captura manual, búsqueda a
partir del 5.º carácter.
"""

from __future__ import annotations

import ast
import re

from tests.architecture.architecture_guardrails import APP_ROOT

_COMPONENT = APP_ROOT / "frontend/desktop/components/address_input.py"
_SERVICE = APP_ROOT / "backend/application/addresses/address_search.py"
_FACTORY = APP_ROOT / "backend/infrastructure/maps/address_search_factory.py"
_MODULES = APP_ROOT / "frontend/desktop/modules"

#: Las pantallas que capturan una dirección. Cada una DEBE usar `AddressInput`.
_ADDRESS_SCREENS = (
    "finance/suppliers/dialogs/supplier_dialogs.py",
    "orders_delivery/pages/new_order_page.py",
    "configuracion/dialogs/company_branch_dialogs.py",
    "customers_crm/dialogs/customer_address_dialog.py",
)

#: Una caja de texto cuyo marcador o nombre accesible dice "dirección", "calle",
#: "colonia" o "código postal" es una dirección capturada a mano, fuera del
#: estándar. (Las zonas de reparto capturan una LISTA de códigos postales, que
#: no es una dirección: se excluyen por nombre de archivo.)
_FREE_TEXT_ADDRESS = re.compile(
    r"StandardLineEdit\([^)]*placeholder=\"(Calle|Colonia|C[oó]digo postal|Direcci[oó]n)",
    re.IGNORECASE)
_EXCLUDED = {"delivery_zone_dialog.py"}


def _text(path) -> str:
    return path.read_text(encoding="utf-8")


def test_every_address_screen_uses_the_standard_component() -> None:
    faltan = [s for s in _ADDRESS_SCREENS
              if "AddressInput" not in _text(_MODULES / s)]
    assert faltan == [], f"Pantallas de dirección sin el componente estándar: {faltan}"


def test_no_module_captures_an_address_with_free_text_boxes() -> None:
    culpables = []
    for archivo in _MODULES.rglob("*.py"):
        if "__pycache__" in archivo.parts or archivo.name in _EXCLUDED:
            continue
        if _FREE_TEXT_ADDRESS.search(_text(archivo)):
            culpables.append(str(archivo.relative_to(APP_ROOT)))
    assert culpables == [], (
        "Direcciones capturadas con cajas de texto libre en vez de AddressInput: "
        f"{culpables}")


def test_the_five_character_minimum_has_a_single_source() -> None:
    """La cifra vive en el servicio; el componente la IMPORTA. Si se repitiera,
    cambiarla en un lado dejaría el otro buscando con otro mínimo."""
    assert re.search(r"^MIN_QUERY_CHARS = 5$", _text(_SERVICE), re.MULTILINE)
    componente = _text(_COMPONENT)
    assert "MIN_QUERY_CHARS" in componente
    assert not re.search(r"^MIN_QUERY_CHARS\s*=", componente, re.MULTILINE)


def test_the_component_never_blocks_the_ui_thread() -> None:
    componente = _text(_COMPONENT)
    for marca in ("QRunnable", "QThreadPool", "_request_id", "QueuedConnection"):
        assert marca in componente, marca
    # Sin proveedor por omisión que devuelva vacío en silencio.
    assert "lambda _query: []" not in componente


def test_the_token_comes_from_integrations_not_the_environment() -> None:
    """La versión perdida leía `MAPBOX_TOKEN` del entorno, que nadie puede
    cambiar desde la aplicación."""
    fabrica = _text(_FACTORY)
    assert "credential_references" in fabrica and "get_secret" in fabrica
    for archivo in (APP_ROOT / "backend/infrastructure/maps").glob("*.py"):
        assert "os.environ" not in _text(archivo), archivo.name
        assert "getenv" not in _text(archivo), archivo.name


def test_the_chain_is_mapbox_then_nominatim() -> None:
    fabrica = _text(_FACTORY)
    assert fabrica.index('("Mapbox"') < fabrica.index('("Nominatim"')


def test_the_ui_never_builds_a_provider_directly() -> None:
    """Las pantallas piden el servicio a la fábrica (vía su presentador); nunca
    construyen `MapboxAddressProvider` ni `NominatimAddressProvider`. Si una lo
    hiciera, se saltaría la configuración de Integraciones."""
    for archivo in (APP_ROOT / "frontend").rglob("*.py"):
        if "__pycache__" in archivo.parts:
            continue
        arbol = ast.parse(_text(archivo))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Name) and nodo.id in (
                    "MapboxAddressProvider", "NominatimAddressProvider"):
                raise AssertionError(f"{archivo.relative_to(APP_ROOT)} construye un "
                                     f"proveedor de mapas directamente")
