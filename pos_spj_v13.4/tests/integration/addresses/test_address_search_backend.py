"""Búsqueda de direcciones — servicio, proveedores, configuración y migración.

Nada aquí toca la red: los proveedores reciben un `http_get` falso. Se prueba lo
que decidió el usuario —Mapbox configurable desde Configuración, respaldo a
Nominatim y luego manual, búsqueda desde el 5.º carácter— y las tres cosas que la
versión perdida hacía mal: confundir "falló" con "sin coincidencias", quedarse
sólo con la etiqueta, y leer el token del entorno.
"""

import importlib
import sqlite3

import pytest

from backend.application.addresses import (
    MIN_QUERY_CHARS,
    AddressProviderError,
    AddressSearchService,
    AddressSearchStatus,
    AddressSource,
    StructuredAddress,
)
from backend.infrastructure.db.schema.integrations_schema import create_integrations_schema
from backend.infrastructure.maps.address_cache import AddressSearchCache
from backend.infrastructure.maps.address_search_factory import build_address_search_service
from backend.infrastructure.maps.mapbox_address_provider import MapboxAddressProvider
from backend.infrastructure.maps.nominatim_address_provider import NominatimAddressProvider

_264 = importlib.import_module("migrations.standalone.264_seed_address_search_integrations")


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _Http:
    def __init__(self, *respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []

    def __call__(self, url, *, params, headers=None, timeout=5.0):
        self.llamadas.append((url, dict(params)))
        r = self._respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class _Fake:
    def __init__(self, code, *, autocomplete=True, result=None, error=None):
        self.code = code
        self.display_name = code.title()
        self.supports_autocomplete = autocomplete
        self.attribution = f"© {code}"
        self._result = result or []
        self._error = error
        self.calls = 0

    def search(self, query, *, limit):
        self.calls += 1
        if self._error:
            raise AddressProviderError(self._error)
        return list(self._result)


class _Secrets:
    def __init__(self, valores=None):
        self._v = dict(valores or {})

    def get_secret(self, nombre):
        return self._v.get(nombre)


_UNA = StructuredAddress(street="Av. Juárez", exterior_number="120", latitude=19.43,
                         longitude=-99.14, source=AddressSource.MAPBOX, label="Av. Juárez 120")

_MAPBOX_V6 = {"features": [{
    "geometry": {"type": "Point", "coordinates": [-99.1478, 19.4351]},
    "properties": {
        "feature_type": "address", "full_address": "Avenida Juárez 120, Centro, CDMX",
        "coordinates": {"latitude": 19.4351, "longitude": -99.1478},
        "context": {
            "address": {"address_number": "120", "street_name": "Avenida Juárez"},
            "street": {"name": "Avenida Juárez"},
            "neighborhood": {"name": "Centro"},
            "postcode": {"name": "06050"},
            "place": {"name": "Cuauhtémoc"},
            "region": {"name": "Ciudad de México"},
            "country": {"country_code": "mx"},
        }}}]}

_NOMINATIM = [{
    "lat": "19.4351", "lon": "-99.1478",
    "display_name": "120, Avenida Juárez, Centro, Cuauhtémoc, CDMX, 06050, México",
    "address": {"house_number": "120", "road": "Avenida Juárez", "suburb": "Centro",
                "city": "Cuauhtémoc", "state": "Ciudad de México", "postcode": "06050",
                "country_code": "mx"}}]


class TestStructuredAddress:
    def test_one_line_for_modules_that_store_a_single_field(self):
        d = StructuredAddress(street="Av. Juárez", exterior_number="120",
                              interior_number="4", neighborhood="Centro",
                              municipality="Cuauhtémoc", state="CDMX", postal_code="06050")
        assert d.one_line() == ("Av. Juárez 120 Int. 4, Col. Centro, Cuauhtémoc, CDMX, "
                                "C.P. 06050")

    def test_manual_is_never_geocoded_even_with_stale_coordinates(self):
        d = StructuredAddress(street="X", latitude=1.0, longitude=2.0,
                              source=AddressSource.MANUAL)
        assert d.is_geocoded is False

    def test_correcting_by_hand_drops_the_coordinates(self):
        manual = _UNA.as_manual()
        assert (manual.latitude, manual.longitude) == (None, None)
        assert manual.street == "Av. Juárez"

    def test_half_a_coordinate_is_discarded(self):
        d = StructuredAddress(street="X", latitude=19.4, source=AddressSource.MAPBOX)
        assert (d.latitude, d.longitude) == (None, None)

    def test_an_impossible_coordinate_is_rejected(self):
        with pytest.raises(ValueError):
            StructuredAddress(street="X", latitude=200, longitude=0)

    def test_a_single_line_is_not_split_by_guessing(self):
        assert StructuredAddress.from_one_line("Juárez 120, Centro").street == \
            "Juárez 120, Centro"


class TestTheChain:
    def test_minimum_is_five_characters(self):
        assert MIN_QUERY_CHARS == 5
        mapbox = _Fake("MAPBOX", result=[_UNA])
        servicio = AddressSearchService([mapbox])
        assert servicio.search("Juár", interactive=True).status is AddressSearchStatus.TOO_SHORT
        assert mapbox.calls == 0
        assert servicio.search("Juáre", interactive=True).status is AddressSearchStatus.OK

    def test_spaces_do_not_count_as_characters(self):
        servicio = AddressSearchService([_Fake("MAPBOX", result=[_UNA])])
        assert servicio.search("  Ju   á  ", interactive=True).status is \
            AddressSearchStatus.TOO_SHORT

    def test_mapbox_first_when_it_works(self):
        mapbox, osm = _Fake("MAPBOX", result=[_UNA]), _Fake("NOMINATIM", autocomplete=False)
        r = AddressSearchService([mapbox, osm]).search("Juárez 120", interactive=False)
        assert r.provider_code == "MAPBOX" and osm.calls == 0

    def test_falls_back_to_nominatim_when_mapbox_fails(self):
        mapbox = _Fake("MAPBOX", error="token inválido o caducado")
        osm = _Fake("NOMINATIM", autocomplete=False, result=[_UNA])
        r = AddressSearchService([mapbox, osm]).search("Juárez 120", interactive=False)
        assert r.status is AddressSearchStatus.OK and r.provider_code == "NOMINATIM"
        assert "token inválido" in r.message

    def test_zero_matches_is_an_answer_not_a_failure(self):
        mapbox = _Fake("MAPBOX", result=[])
        osm = _Fake("NOMINATIM", autocomplete=False, result=[_UNA])
        r = AddressSearchService([mapbox, osm]).search("Calle inexistente", interactive=False)
        assert r.status is AddressSearchStatus.NO_RESULTS and osm.calls == 0

    def test_nominatim_is_never_called_while_typing(self):
        mapbox = _Fake("MAPBOX", error="sin conexión con el servicio")
        osm = _Fake("NOMINATIM", autocomplete=False, result=[_UNA])
        r = AddressSearchService([mapbox, osm]).search("Juárez 120", interactive=True)
        assert r.status is AddressSearchStatus.NEEDS_EXPLICIT_SEARCH
        assert osm.calls == 0
        assert "Enter" in r.message and "sin conexión" in r.message

    def test_everything_down_ends_in_manual_capture(self):
        r = AddressSearchService([
            _Fake("MAPBOX", error="servicio no disponible"),
            _Fake("NOMINATIM", autocomplete=False, error="servicio no disponible"),
        ]).search("Juárez 120", interactive=False)
        assert r.status is AddressSearchStatus.UNAVAILABLE
        assert "manualmente" in r.message

    def test_a_provider_that_crashes_does_not_break_the_chain(self):
        class _Revienta(_Fake):
            def search(self, query, *, limit):
                raise RuntimeError("bug")
        osm = _Fake("NOMINATIM", autocomplete=False, result=[_UNA])
        r = AddressSearchService([_Revienta("MAPBOX"), osm]).search(
            "Juárez 120", interactive=False)
        assert r.provider_code == "NOMINATIM"

    def test_not_configured_says_where_to_configure_it(self):
        r = AddressSearchService([]).search("Juárez 120", interactive=False)
        assert r.status is AddressSearchStatus.NOT_CONFIGURED
        assert "Integraciones" in r.message

    def test_results_are_cached(self):
        mapbox = _Fake("MAPBOX", result=[_UNA])
        servicio = AddressSearchService([mapbox], cache=AddressSearchCache())
        servicio.search("Juárez 120", interactive=True)
        servicio.search("juárez  120", interactive=True)
        assert mapbox.calls == 1

    def test_autocomplete_depends_on_the_first_provider(self):
        assert AddressSearchService([_Fake("MAPBOX")]).autocomplete_available()
        assert not AddressSearchService(
            [_Fake("NOMINATIM", autocomplete=False)]).autocomplete_available()


class TestCache:
    def test_it_expires(self):
        reloj = [0.0]
        cache = AddressSearchCache(ttl_seconds=10, clock=lambda: reloj[0])
        cache.put("k", 1)
        reloj[0] = 11
        assert cache.get("k") is None

    def test_it_evicts_the_least_recently_used(self):
        cache = AddressSearchCache(max_size=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")
        cache.put("c", 3)
        assert cache.get("b") is None and cache.get("a") == 1


class TestMapbox:
    def test_it_fills_the_structured_fields_not_just_the_label(self):
        http = _Http(_Resp(200, _MAPBOX_V6))
        d = MapboxAddressProvider(token="pk.x", http_get=http).search("Juárez 120", limit=5)[0]
        assert (d.street, d.exterior_number, d.neighborhood, d.municipality, d.state,
                d.postal_code, d.country_code) == (
            "Avenida Juárez", "120", "Centro", "Cuauhtémoc", "Ciudad de México", "06050", "MX")
        assert (d.latitude, d.longitude) == (19.4351, -99.1478)
        assert d.source is AddressSource.MAPBOX and d.is_geocoded

    def test_it_asks_for_permanent_geocoding_by_default(self):
        http = _Http(_Resp(200, {"features": []}))
        MapboxAddressProvider(token="pk.x", http_get=http).search("Juárez 120", limit=5)
        params = http.llamadas[0][1]
        assert params["permanent"] == "true" and params["country"] == "mx"

    @pytest.mark.parametrize("estado,motivo", [
        (401, "token inválido"), (403, "acceso denegado"), (429, "límite"),
        (503, "no disponible")])
    def test_failures_raise_instead_of_returning_empty(self, estado, motivo):
        with pytest.raises(AddressProviderError, match=motivo):
            MapboxAddressProvider(token="pk.x", http_get=_Http(_Resp(estado))).search(
                "Juárez 120", limit=5)

    def test_a_network_error_raises_too(self):
        with pytest.raises(AddressProviderError, match="sin conexión"):
            MapboxAddressProvider(token="pk.x", http_get=_Http(OSError("red"))).search(
                "Juárez 120", limit=5)

    def test_without_token_it_cannot_be_built(self):
        with pytest.raises(AddressProviderError):
            MapboxAddressProvider(token="  ")


class TestNominatim:
    def test_it_fills_the_structured_fields(self):
        prov = NominatimAddressProvider(http_get=_Http(_Resp(200, _NOMINATIM)),
                                        sleep=lambda s: None)
        d = prov.search("Juárez 120", limit=5)[0]
        assert (d.street, d.exterior_number, d.neighborhood, d.municipality,
                d.postal_code) == ("Avenida Juárez", "120", "Centro", "Cuauhtémoc", "06050")
        assert d.source is AddressSource.NOMINATIM and d.is_geocoded

    def test_in_mexico_city_the_alcaldia_is_the_municipality(self):
        """Forma REAL de la respuesta para CDMX (consulta del 2026-09-17): la
        alcaldía viene en `borough` y `city` repite el estado."""
        payload = [{"lat": "19.434994", "lon": "-99.1490767", "display_name": "x",
                    "address": {"house_number": "100", "road": "Avenida Juárez",
                                "neighbourhood": "Centro", "city": "Ciudad de México",
                                "borough": "Cuauhtémoc", "state": "Ciudad de México",
                                "postcode": "06040", "country_code": "mx"}}]
        d = NominatimAddressProvider.parse(payload)[0]
        assert (d.municipality, d.state, d.neighborhood) == (
            "Cuauhtémoc", "Ciudad de México", "Centro")

    def test_it_declares_no_autocomplete_and_shows_attribution(self):
        assert NominatimAddressProvider.supports_autocomplete is False
        assert "OpenStreetMap" in NominatimAddressProvider.attribution

    def test_it_waits_one_second_between_requests(self):
        reloj, esperas = [100.0], []

        def dormir(s):
            esperas.append(s)
            reloj[0] += s

        prov = NominatimAddressProvider(
            http_get=_Http(_Resp(200, []), _Resp(200, [])),
            clock=lambda: reloj[0], sleep=dormir)
        prov.search("Juárez 120", limit=5)
        prov.search("Juárez 121", limit=5)
        assert esperas and esperas[-1] == pytest.approx(1.0, abs=0.01)

    def test_being_throttled_is_a_failure(self):
        prov = NominatimAddressProvider(http_get=_Http(_Resp(429)), sleep=lambda s: None)
        with pytest.raises(AddressProviderError, match="limitó"):
            prov.search("Juárez 120", limit=5)

    def test_contact_email_is_sent_when_configured(self):
        http = _Http(_Resp(200, []))
        NominatimAddressProvider(contact_email="ti@tienda.mx", http_get=http,
                                 sleep=lambda s: None).search("Juárez 120", limit=5)
        assert http.llamadas[0][1]["email"] == "ti@tienda.mx"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_integrations_schema(c)
    _264.run(c)
    yield c
    c.close()


def _instancia(conn, code):
    from backend.infrastructure.db.repositories.integrations.integration_definition_repository import (
        SqliteIntegrationDefinitionRepository,
    )
    from backend.infrastructure.db.repositories.integrations.integration_instance_repository import (
        SqliteIntegrationInstanceRepository,
    )
    definicion = SqliteIntegrationDefinitionRepository(conn).get_by_code(code)
    repo = SqliteIntegrationInstanceRepository(conn)
    return definicion, repo, repo.list_by_definition(definicion.id)[0]


def _activar_mapbox(conn):
    _d, repo, mapbox = _instancia(conn, "MAPBOX")
    mapbox.activate()
    repo.save(mapbox)
    conn.commit()


class TestConfiguredFromIntegrations:
    def test_the_migration_seeds_both_integrations(self, conn):
        mapbox_def, _r, mapbox = _instancia(conn, "MAPBOX")
        osm_def, _r2, osm = _instancia(conn, "NOMINATIM")
        assert mapbox_def.category.value == osm_def.category.value == "LOCATION"
        assert mapbox_def.required_credential_names == ("mapbox_access_token",)
        assert mapbox.active is False and osm.active is True
        assert mapbox.config["permanent"] is True

    def test_the_migration_is_idempotent_and_respects_admin_changes(self, conn):
        _activar_mapbox(conn)
        _264.run(conn)
        assert _instancia(conn, "MAPBOX")[2].active is True
        assert conn.execute("SELECT COUNT(*) FROM integration_definitions").fetchone()[0] == 2

    def test_fresh_install_uses_only_the_fallback(self, conn):
        servicio = build_address_search_service(conn, secret_store=_Secrets())
        assert [p.code for p in servicio.providers] == ["NOMINATIM"]

    def test_activating_mapbox_with_a_token_puts_it_first(self, conn):
        _activar_mapbox(conn)
        servicio = build_address_search_service(
            conn, secret_store=_Secrets({"mapbox_access_token": "pk.real"}))
        assert [p.code for p in servicio.providers] == ["MAPBOX", "NOMINATIM"]
        assert servicio.autocomplete_available()

    def test_active_but_without_token_is_skipped_not_broken(self, conn):
        _activar_mapbox(conn)
        servicio = build_address_search_service(conn, secret_store=_Secrets())
        assert [p.code for p in servicio.providers] == ["NOMINATIM"]

    def test_the_admin_can_switch_the_fallback_off(self, conn):
        _d, repo, osm = _instancia(conn, "NOMINATIM")
        osm.deactivate()
        repo.save(osm)
        conn.commit()
        servicio = build_address_search_service(conn, secret_store=_Secrets())
        assert servicio.providers == ()
        assert servicio.search("Juárez 120", interactive=False).status is \
            AddressSearchStatus.NOT_CONFIGURED

    def test_the_token_is_never_read_from_the_environment(self, conn, monkeypatch):
        monkeypatch.setenv("MAPBOX_TOKEN", "pk.del_entorno")
        _activar_mapbox(conn)
        servicio = build_address_search_service(conn, secret_store=_Secrets())
        assert "MAPBOX" not in [p.code for p in servicio.providers]

    def test_a_broken_secret_store_never_blocks_the_screen(self, conn):
        _activar_mapbox(conn)

        class _Roto:
            def get_secret(self, nombre):
                raise RuntimeError("almacén caído")

        servicio = build_address_search_service(conn, secret_store=_Roto())
        assert [p.code for p in servicio.providers] == ["NOMINATIM"]

    def test_without_the_integrations_schema_the_fallback_still_works(self):
        c = sqlite3.connect(":memory:")
        servicio = build_address_search_service(c, secret_store=_Secrets())
        assert [p.code for p in servicio.providers] == ["NOMINATIM"]
        c.close()
