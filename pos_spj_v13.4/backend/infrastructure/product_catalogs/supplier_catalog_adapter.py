"""Supplier catalog adapter (§15).

Maps a supplier's catalog payload to the canonical record dict via a configurable
field map (each supplier uses different keys). Fetch is abstracted behind an
injected client so the adapter is network-free in tests.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.products.exceptions import ExternalCatalogUnavailableError
from backend.domain.products.external_enums import ExternalProviderType
from backend.infrastructure.product_catalogs.external_record_normalizer import normalize

_DEFAULT_FIELD_MAP = {
    "external_id": "supplier_sku", "name": "description", "barcode": "ean",
    "brand": "brand", "category": "family", "net_weight": "weight", "unit": "uom",
}


class RawCatalogClient(Protocol):
    def fetch(self, query: str) -> list[dict]: ...


class SupplierCatalogAdapter:
    provider_type = ExternalProviderType.SUPPLIER

    def __init__(self, client: RawCatalogClient,
                 field_map: dict[str, str] | None = None) -> None:
        self._client = client
        self._field_map = field_map or _DEFAULT_FIELD_MAP

    def search(self, query: str) -> list[dict]:
        try:
            raw_items = self._client.fetch(query)
        except Exception as exc:
            raise ExternalCatalogUnavailableError(
                f"Catálogo de proveedor no disponible: {exc}") from exc
        return [normalize(item, self._field_map) for item in raw_items]
