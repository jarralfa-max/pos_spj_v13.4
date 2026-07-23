"""Open Food Facts adapter (§15).

Maps OFF product JSON to the canonical record dict. The HTTP fetch is abstracted
behind an injected client (``fetch(query) -> list[dict]``) so the adapter is
testable without network and honours the environment proxy when a real client is
wired.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.products.exceptions import ExternalCatalogUnavailableError
from backend.domain.products.external_enums import ExternalProviderType
from backend.infrastructure.product_catalogs.external_record_normalizer import normalize

_OFF_FIELD_MAP = {
    "external_id": "code", "name": "product_name", "barcode": "code",
    "brand": "brands", "category": "categories", "net_weight": "quantity",
    "unit": "product_quantity_unit",
}


class RawCatalogClient(Protocol):
    def fetch(self, query: str) -> list[dict]: ...


class OpenFoodFactsAdapter:
    provider_type = ExternalProviderType.OPEN_FOOD_FACTS

    def __init__(self, client: RawCatalogClient) -> None:
        self._client = client

    def search(self, query: str) -> list[dict]:
        try:
            raw_products = self._client.fetch(query)
        except Exception as exc:  # network/proxy failure surfaces as domain error
            raise ExternalCatalogUnavailableError(
                f"Open Food Facts no disponible: {exc}") from exc
        return [normalize(p, _OFF_FIELD_MAP) for p in raw_products]
