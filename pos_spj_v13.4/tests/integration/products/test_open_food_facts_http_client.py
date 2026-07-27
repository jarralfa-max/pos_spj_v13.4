"""§15 — cliente HTTP real de Open Food Facts (transporte inyectable, sin red)."""

import pytest

from backend.domain.products.entities.external_catalog_source import (
    ExternalCatalogSource,
)
from backend.domain.products.exceptions import ExternalCatalogUnavailableError
from backend.domain.products.external_enums import ExternalProviderType
from backend.infrastructure.product_catalogs.catalog_wiring import (
    build_default_registry,
    build_open_food_facts_adapter,
)
from backend.infrastructure.product_catalogs.external_product_catalog_gateway import (
    ExternalProductCatalogGateway,
)
from backend.infrastructure.product_catalogs.open_food_facts_http_client import (
    OpenFoodFactsHttpClient,
)


class _Transport:
    """Records the calls and replays scripted (status, payload) responses."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, url, params):
        self.calls.append((url, params))
        return self._responses.pop(0)


_PRODUCT = {"code": "7501055310333", "product_name": "Coca-Cola",
            "brands": "Coca-Cola", "categories": "Bebidas",
            "quantity": "600", "product_quantity_unit": "ml"}


def test_empty_query_short_circuits():
    t = _Transport()
    assert OpenFoodFactsHttpClient(transport=t).fetch("   ") == []
    assert t.calls == []  # no network call


def test_keyword_search_hits_search_endpoint():
    t = _Transport((200, {"products": [_PRODUCT], "count": 1}))
    out = OpenFoodFactsHttpClient(transport=t).fetch("coca cola")
    assert out == [_PRODUCT]
    url, params = t.calls[0]
    assert url.endswith("/cgi/search.pl")
    assert params["search_terms"] == "coca cola" and params["json"] == 1


def test_barcode_query_hits_product_endpoint():
    t = _Transport((200, {"status": 1, "product": _PRODUCT}))
    out = OpenFoodFactsHttpClient(transport=t).fetch("7501055310333")
    assert out == [_PRODUCT]
    url, _params = t.calls[0]
    assert url.endswith("/api/v2/product/7501055310333.json")


def test_barcode_not_found_returns_empty():
    t = _Transport((200, {"status": 0, "product": None}))
    assert OpenFoodFactsHttpClient(transport=t).fetch("7501055310333") == []


def test_barcode_404_is_empty_not_failure():
    t = _Transport((404, {}))
    assert OpenFoodFactsHttpClient(transport=t).fetch("00000000") == []


def test_http_error_raises():
    t = _Transport((503, {}))
    with pytest.raises(ConnectionError):
        OpenFoodFactsHttpClient(transport=t).fetch("agua")


def test_missing_products_key_is_empty():
    t = _Transport((200, {"count": 0}))
    assert OpenFoodFactsHttpClient(transport=t).fetch("nada") == []


def test_page_size_is_bounded():
    t = _Transport((200, {"products": []}))
    OpenFoodFactsHttpClient(page_size=9999, transport=t).fetch("x")
    assert t.calls[0][1]["page_size"] == 100


# ── end-to-end through adapter + gateway ─────────────────────────────────────
def _source():
    return ExternalCatalogSource(code="OFF", name="Open Food Facts",
                                 provider_type=ExternalProviderType.OPEN_FOOD_FACTS)


def test_wiring_end_to_end_maps_to_domain_record():
    client = OpenFoodFactsHttpClient(
        transport=_Transport((200, {"products": [_PRODUCT]})))
    gateway = ExternalProductCatalogGateway(build_default_registry(client))
    records = gateway.search(_source(), "coca")
    assert len(records) == 1
    rec = records[0]
    assert rec.barcode == "7501055310333"
    assert rec.name == "Coca-Cola" and rec.brand == "Coca-Cola"
    assert rec.data_quality_score.value > 0


def test_wiring_surfaces_network_failure_as_domain_error():
    class _Boom:
        def fetch(self, q):
            raise ConnectionError("proxy down")

    gateway = ExternalProductCatalogGateway(build_default_registry(_Boom()))
    with pytest.raises(ExternalCatalogUnavailableError):
        gateway.search(_source(), "x")


def test_build_adapter_defaults_to_live_client():
    adapter = build_open_food_facts_adapter()
    assert adapter.provider_type is ExternalProviderType.OPEN_FOOD_FACTS
    assert isinstance(adapter._client, OpenFoodFactsHttpClient)
